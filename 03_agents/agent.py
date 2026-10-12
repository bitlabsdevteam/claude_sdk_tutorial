"""3.2 A bounded agent loop: max turns, token/cost budget, timeout, explicit stop reasons."""
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.budget import Budget, estimate_cost
from common.config import MODEL, make_client
from common.demo_tools import TOOLS, run_tool


@dataclass
class AgentResult:
    stop: str  # done | refusal | truncated | max_turns | max_tokens | max_cost | timeout
    text: str
    messages: list


def log_turn(turn: int, response, budget: Budget) -> None:
    u = response.usage
    print(json.dumps({
        "turn": turn, "stop_reason": response.stop_reason,
        "in": u.input_tokens, "out": u.output_tokens,
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
        "total_tokens": budget.tokens, "cost_usd": round(budget.cost_usd, 4),
        "request_id": getattr(response, "_request_id", None),
    }))


def text_of(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text")


def run_agent(client, messages: list, tools: list, execute=run_tool, budget: Budget | None = None,
              system: str | None = None, model: str = MODEL, tracer=None, on_turn=None, stop_if=None,
              **create_kwargs) -> AgentResult:
    """Loop until the model finishes or any limit trips. Never raises for budget reasons.

    Optional hooks (all default to off):
      tracer   - records one structured entry per turn, including tool timings (common/tracing.py)
      on_turn  - called with `messages` at each CONSISTENT boundary (every tool_use has its tool_result),
                 which is the only safe moment to checkpoint (common/checkpoint.py)
      stop_if  - returns a reason string to stop the run (e.g. a loop guard tripped), else None
    """
    budget = budget or Budget()
    text = ""
    while True:
        if (limit := budget.exceeded() or (stop_if() if stop_if else None)):
            return AgentResult(limit, text, messages)  # checked BEFORE spending on another call

        kwargs = {"system": system} if system else {}
        started = time.monotonic()
        response = client.messages.create(
            model=model, max_tokens=4096, tools=tools, messages=messages,
            timeout=max(1.0, budget.remaining_s()),  # a hung request can't outlive the deadline
            output_config={"effort": "low"}, **kwargs, **create_kwargs,
        )
        latency = time.monotonic() - started
        budget.record(response.usage, model)
        log_turn(budget.turns, response, budget)
        text = text_of(response) or text

        def trace(tool_log: list) -> None:
            if tracer:
                tracer.turn(turn=budget.turns, model=model, response=response, latency_s=latency,
                            cost_usd=estimate_cost(response.usage, model), tools=tool_log)

        # Check stop_reason before trusting content.
        if response.stop_reason == "refusal":
            trace([])
            return AgentResult("refusal", text, messages)
        if response.stop_reason == "max_tokens":
            trace([])
            return AgentResult("truncated", text, messages)
        if response.stop_reason != "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            trace([])
            if on_turn:
                on_turn(messages)
            return AgentResult("done", text, messages)

        messages.append({"role": "assistant", "content": response.content})
        results, tool_log = [], []
        for block in (b for b in response.content if b.type == "tool_use"):
            t0 = time.monotonic()
            content, is_error = execute(block.name, block.input)
            tool_log.append({"name": block.name, "is_error": bool(is_error),
                             "duration_s": round(time.monotonic() - t0, 4), "result_chars": len(content)})
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": content, "is_error": is_error})
        messages.append({"role": "user", "content": results})  # all results in ONE message
        trace(tool_log)
        if on_turn:
            on_turn(messages)  # every tool_use now has its tool_result: a valid place to save state


def main() -> None:
    budget = Budget(max_turns=6, max_total_tokens=40_000, max_cost_usd=0.25, timeout_s=90)
    task = "What is the weather in Paris (celsius), and what is that temperature squared?"
    result = run_agent(make_client(), [{"role": "user", "content": task}], TOOLS, budget=budget)
    print(f"[stop] {result.stop} after {budget.turns} turns, ~${budget.cost_usd:.4f}")
    print(result.text)


if __name__ == "__main__":
    main()
