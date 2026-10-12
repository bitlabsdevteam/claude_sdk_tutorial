"""The harness core: every tool call goes policy -> pre-hooks -> tool -> post-hooks, and is traced.

`Harness.execute(name, input)` has the same shape as the `execute` argument of `03_agents/agent.py::run_agent`,
so any agent loop gets permissions, hooks and tracing by passing `harness.execute`.

Why a harness and not "tell the model to be careful": a prompt is a request, a policy is enforcement.
The model can be wrong, confused, or manipulated (prompt injection); the harness still says no.
"""
import fnmatch
from dataclasses import dataclass
from typing import Callable, Literal

from common.demo_tools import ToolError
from common.tracing import Tracer

Verdict = Literal["allow", "ask", "deny"]


@dataclass
class Rule:
    tool: str  # tool name or fnmatch pattern ("read_*", "*")
    verdict: Verdict
    when: Callable[[dict], bool] | None = None  # applies only if this returns True for the call's arguments
    reason: str = ""


@dataclass
class Decision:
    verdict: Verdict
    reason: str


class Policy:
    """First matching rule wins. No match means `default` (deny): a new tool is unusable until someone allows it."""

    def __init__(self, rules: list[Rule], default: Verdict = "deny", destructive: set[str] | None = None):
        self.rules, self.default, self.destructive = rules, default, destructive or set()

    def decide(self, name: str, args: dict) -> Decision:
        decision = Decision(self.default, "no rule matched (default)")
        for rule in self.rules:
            if fnmatch.fnmatch(name, rule.tool) and (rule.when is None or rule.when(args)):
                decision = Decision(rule.verdict, rule.reason or f"rule '{rule.tool}'")
                break
        if name in self.destructive and decision.verdict == "allow":
            # Irreversible actions are never auto-approved, whatever the rules say.
            decision = Decision("ask", f"'{name}' is destructive: needs human approval")
        return decision


class Block(Exception):
    """Raised by a pre-hook to stop a call. The message goes back to the model as the tool error.
    `kind` names the trace event (e.g. "taint_block", "loop_warning") so triage can tell causes apart."""

    def __init__(self, message: str, kind: str = "blocked"):
        super().__init__(message)
        self.kind = kind


PreHook = Callable[[str, dict], dict]  # (name, args) -> args (possibly rewritten); raise Block to stop
PostHook = Callable[[str, dict, str, bool], str]  # (name, args, result, is_error) -> result (possibly rewritten)


class Harness:
    def __init__(self, handlers: dict[str, Callable], policy: Policy, approve: Callable[[str, dict], bool] | None = None,
                 pre_hooks: list[PreHook] | None = None, post_hooks: list[PostHook] | None = None,
                 tracer: Tracer | None = None):
        self.handlers, self.policy, self.approve = handlers, policy, approve
        self.pre_hooks, self.post_hooks = pre_hooks or [], post_hooks or []
        self.tracer = tracer or Tracer()

    def _deny(self, name: str, kind: str, reason: str, label: str = "Denied") -> tuple[str, bool]:
        self.tracer.event(kind, tool=name, reason=reason)
        # Denials are tool ERRORS, not crashes: the model reads the reason and can adapt or ask the user.
        return f"{label}: {reason}. Do not retry this call; tell the user or choose another approach.", True

    def execute(self, name: str, args: dict) -> tuple[str, bool]:
        decision = self.policy.decide(name, args)
        if decision.verdict == "deny":
            return self._deny(name, "denied", decision.reason)
        if decision.verdict == "ask":
            # No approver configured means no approval: fail closed.
            if self.approve is None or not self.approve(name, args):
                return self._deny(name, "denied", f"approval required and not granted ({decision.reason})")
            self.tracer.event("approved", tool=name)

        try:
            for hook in self.pre_hooks:
                args = hook(name, args)
        except Block as e:
            return self._deny(name, e.kind, str(e), label="Blocked")

        handler = self.handlers.get(name)
        if handler is None:
            return f"Unknown tool '{name}'. Available: {', '.join(self.handlers)}.", True
        try:
            result, is_error = handler(**args), False
        except ToolError as e:  # recoverable: the message is written for the model
            result, is_error = str(e), True
        except TypeError as e:  # wrong or missing arguments
            result, is_error = f"Invalid arguments for {name}: {e}", True
        except Exception as e:  # unexpected: log details for us, show only a generic message to the model
            self.tracer.event("tool_crash", tool=name, error=type(e).__name__)
            result, is_error = f"{name} failed unexpectedly.", True

        for hook in self.post_hooks:
            result = hook(name, args, result, is_error)
        return result, is_error
