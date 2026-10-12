"""6.9 Permissions: allow / ask / deny per tool and per argument, default deny, human approval for the risky.

Policy lives in the harness (common/harness.py), NOT in the prompt: the model can be wrong or manipulated,
the policy still says no. Run with no flags for an offline walkthrough, or `--live` for a budgeted agent run
that really asks you on stdin before deleting a file.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded loop from Level 3

from common.harness import Harness, Policy, Rule
from common.workspace_tools import make_workspace


def default_policy() -> Policy:
    return Policy(
        rules=[
            Rule("list_files", "allow"),
            # Argument-aware rules: order matters, first match wins, so specific denials go first.
            Rule("read_file", "deny", when=lambda a: Path(a["path"]).name.startswith("."), reason="hidden files are off limits"),
            Rule("read_file", "allow"),
            Rule("write_file", "allow", when=lambda a: a["path"].endswith((".txt", ".md")), reason="text files are low risk"),
            Rule("write_file", "ask", reason="writing non-text files needs approval"),
            Rule("delete_file", "allow"),  # even if a rule allows it, `destructive` below forces approval
        ],
        default="deny",  # anything not listed (a new tool, a typo) is unusable until someone allows it
        destructive={"delete_file"},
    )


def cli_approver(name: str, args: dict) -> bool:
    """A human gate. Anything but an explicit yes is a no."""
    return input(f"  APPROVE {name}({args})? [y/N] ").strip().lower() == "y"


def walkthrough() -> None:
    policy = default_policy()
    calls = [("list_files", {}), ("read_file", {"path": "notes.txt"}), ("read_file", {"path": ".env"}),
             ("write_file", {"path": "a.txt", "content": "x"}), ("write_file", {"path": "run.sh", "content": "x"}),
             ("delete_file", {"path": "a.txt"}), ("send_email", {"to": "x"})]
    for name, args in calls:
        d = policy.decide(name, args)
        print(f"{name:>12} {str(args)[:34]:<36} -> {d.verdict:<5} ({d.reason})")

    print("\nThrough the harness, deleting with no approver / a refusing approver / an approving one:")
    with tempfile.TemporaryDirectory() as tmp:
        schemas, handlers = make_workspace(tmp)
        (Path(tmp) / "old.txt").write_text("old")
        for label, approve in [("no approver", None), ("human says no", lambda n, a: False), ("human says yes", lambda n, a: True)]:
            (Path(tmp) / "old.txt").write_text("old")
            out = Harness(handlers, default_policy(), approve=approve).execute("delete_file", {"path": "old.txt"})
            print(f"  {label:>15}: {out[0][:75]!r} exists_after={(Path(tmp) / 'old.txt').exists()}")


def live() -> None:
    from agent import run_agent

    from common.budget import Budget
    from common.config import make_client

    with tempfile.TemporaryDirectory() as tmp:
        schemas, handlers = make_workspace(tmp)
        (Path(tmp) / "old.txt").write_text("outdated notes")
        harness = Harness(handlers, default_policy(), approve=cli_approver)
        budget = Budget(max_turns=8, max_total_tokens=40_000, max_cost_usd=0.25, timeout_s=120)
        task = "Write a one-line haiku to notes.txt, then delete old.txt."
        result = run_agent(make_client(), [{"role": "user", "content": task}], schemas, harness.execute, budget)
        print(f"[stop] {result.stop} | {result.text}\nevents: {[(e['kind'], e.get('tool')) for e in harness.tracer.records]}")


if __name__ == "__main__":
    live() if "--live" in sys.argv else walkthrough()
