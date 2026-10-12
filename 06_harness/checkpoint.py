"""6.12 Checkpointing and idempotency: crash in the middle, resume, and do not repeat side effects.

Two failure windows matter. (1) A crash BETWEEN turns: restore the saved history and continue. (2) A crash
INSIDE a tool round, after a side effect (an email was sent) but before the round was saved: on resume the
model re-issues that round, so without a journal the email goes out twice.

Offline demo with a scripted model (free): `python 06_harness/checkpoint.py`
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded loop from Level 3

from agent import run_agent

from common.budget import Budget
from common.checkpoint import Journal, RunStore
from common.scripted import RuleModel, text, tool_use


class SimulatedCrash(Exception):
    """Stands in for a process kill, a deploy, or a lost connection."""


def build_tools(outbox: list, crash_on: str | None):
    """Two tools: `send_email` (side effect) and `update_crm`, which can be told to crash."""
    def execute(name: str, args: dict) -> tuple[str, bool]:
        if name == "send_email":
            outbox.append(args["to"])  # the real-world effect we must not repeat
            return f"sent to {args['to']}", False
        if name == "update_crm":
            if crash_on == "update_crm":
                raise SimulatedCrash("process died during update_crm")
            return "crm updated", False
        if name == "lookup":
            return "customer: ada@example.com", False
        return f"unknown tool {name}", True
    return execute


# What the model does after 0, 1, 2 completed rounds. Round 2 has TWO calls: the side effect, then the crashy one.
SCRIPT = [
    [tool_use("a1", "lookup", id="42")],
    [tool_use("b1", "send_email", to="ada@example.com"), tool_use("b2", "update_crm", id="42")],
    [text("Customer notified and CRM updated.")],
]
SCHEMA = []  # the scripted model ignores tool schemas


def attempt(workdir: Path, outbox: list, crash_on: str | None, run_id: str = "demo"):
    store, journal = RunStore(workdir, run_id), Journal(workdir / "journal.json", {"send_email"})
    execute = journal.wrap(build_tools(outbox, crash_on))
    saved = store.load()
    messages = saved[0] if saved else [{"role": "user", "content": "Email Ada and update her CRM record."}]
    budget = Budget(**({"turns": saved[1]["turns"], "tokens": saved[1]["tokens"], "cost_usd": saved[1]["cost_usd"]} if saved else {}))
    print(f"  {'RESUMING' if saved else 'STARTING'} with {len(messages)} saved message(s)")
    result = run_agent(RuleModel(SCRIPT), messages, SCHEMA, execute, budget, on_turn=lambda m: store.save(m, budget))
    return result, journal


def main() -> None:
    outbox: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        print("Run 1 (crashes inside round 2, AFTER the email was sent):")
        try:
            attempt(work, outbox, crash_on="update_crm")
        except SimulatedCrash as e:
            print(f"  CRASH: {e}")
        print(f"  emails sent so far: {outbox}")
        print("Run 2 (resume from the checkpoint):")
        result, journal = attempt(work, outbox, crash_on=None)
        print(f"  result: {result.stop} - {result.text}")
        print(f"  emails sent in total: {outbox} (replayed from journal: {journal.replayed})")
        assert len(outbox) == 1, "the side effect must happen exactly once"
        print("exactly-once holds. Now remove the Journal wrap and watch the email go out twice.")


if __name__ == "__main__":
    main()
