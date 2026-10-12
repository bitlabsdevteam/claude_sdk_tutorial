"""6.10 Hooks: code that runs before and after every tool call to block, rewrite, redact, or audit.

Order is fixed: policy, pre-hooks, tool, post-hooks (common/harness.py). Use a hook for rules that are
about the DATA in a call ("no secrets in file content"), and the policy for rules about WHICH tool runs.
Run with no flags for an offline walkthrough, or `--live` for a budgeted agent run.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded loop from Level 3

from common.harness import Block, Harness, Policy, Rule
from common.tracing import SECRET, Tracer, scrub
from common.workspace_tools import make_workspace

MAX_RESULT_CHARS = 1_000


def block_secrets_in_args(name: str, args: dict) -> dict:
    """Pre-hook: stop a credential from being written anywhere (e.g. after a prompt injection)."""
    if any(isinstance(v, str) and SECRET.search(v) for v in args.values()):
        raise Block("arguments contain what looks like a credential")  # the model sees this message
    return args


def normalize_path(name: str, args: dict) -> dict:
    """Pre-hook that REWRITES the input: './notes.txt' and 'notes.txt' are the same file."""
    if isinstance(args.get("path"), str) and args["path"].startswith("./"):
        return {**args, "path": args["path"][2:]}
    return args


def redact_secrets(name: str, args: dict, result: str, is_error: bool) -> str:
    """Post-hook: whatever a tool returns, credentials never reach the model's context."""
    return scrub(result)


def cap_result(name: str, args: dict, result: str, is_error: bool) -> str:
    """Post-hook: bound what one tool call can add to the context (and say so)."""
    if len(result) > MAX_RESULT_CHARS:
        return result[:MAX_RESULT_CHARS] + f"\n[truncated: {len(result) - MAX_RESULT_CHARS} more chars]"
    return result


def make_audit_hook(tracer: Tracer):
    """Pre-hook that records WHAT was called (tool and argument names, never values) in the trace."""
    def audit(name: str, args: dict) -> dict:
        tracer.event("call", tool=name, arg_names=",".join(sorted(args)))
        return args
    return audit


def build_harness(handlers: dict, tracer: Tracer | None = None) -> Harness:
    tracer = tracer or Tracer()
    policy = Policy([Rule("*", "allow")])  # hooks are the point here, so the policy is permissive
    return Harness(handlers, policy, tracer=tracer,
                   pre_hooks=[make_audit_hook(tracer), normalize_path, block_secrets_in_args],
                   post_hooks=[redact_secrets, cap_result])


def walkthrough() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        schemas, handlers = make_workspace(tmp)
        (Path(tmp) / "config.txt").write_text("db=prod token=Bearer abc123secret")
        h = build_harness(handlers)
        steps = [("rewrite", "write_file", {"path": "./a.txt", "content": "hello"}),
                 ("block", "write_file", {"path": "b.txt", "content": "key sk-ant-abcdefghij12345"}),
                 ("redact", "read_file", {"path": "config.txt"}),
                 ("big file", "write_file", {"path": "big.txt", "content": "x" * 3000})]  # read back below: capped
        for label, name, args in steps:
            print(f"{label:>8}: {h.execute(name, args)}")
        print("rewritten file exists:", (Path(tmp) / "a.txt").exists(), "| secret file written:", (Path(tmp) / "b.txt").exists())
        print("read big.txt ->", len(h.execute("read_file", {"path": "big.txt"})[0]), "chars (capped)")
        print("trace kinds:", [r["kind"] for r in h.tracer.records])


def live() -> None:
    from agent import run_agent

    from common.budget import Budget
    from common.config import make_client

    with tempfile.TemporaryDirectory() as tmp:
        schemas, handlers = make_workspace(tmp)
        h = build_harness(handlers)
        task = "Save the text 'my key is sk-ant-abcdefghij12345' to secret.txt, then list the files."
        result = run_agent(make_client(), [{"role": "user", "content": task}], schemas, h.execute,
                           Budget(max_turns=6, max_total_tokens=30_000, max_cost_usd=0.20, timeout_s=90))
        print(f"[stop] {result.stop} | {result.text}\ntrace kinds: {[r['kind'] for r in h.tracer.records]}")


if __name__ == "__main__":
    live() if "--live" in sys.argv else walkthrough()
