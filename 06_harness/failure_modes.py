"""6.14 Failure taxonomy: stuck loops, error spirals, hallucinated success. Detect them in the harness.

An agent that fails rarely crashes: it keeps going. The harness has to notice. Four scenarios run offline with a
scripted model (free). Each prints how the run ended and what the trace says.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded loop from Level 3

from agent import run_agent

from common.budget import Budget
from common.guards import LoopGuard
from common.harness import Harness, Policy, Rule
from common.scripted import RuleModel, text, tool_use
from common.tracing import Tracer, triage
from common.workspace_tools import make_workspace


def judge(result, verifier) -> str:
    """Never trust "done": the harness checks the outcome itself (same idea as 3.8's run-the-tests step)."""
    if result.stop != "done":
        return f"run ended early: {result.stop}"
    return "verified" if verifier() else "FAILED VERIFICATION (the model claimed success; the check disagrees)"


# Each scenario is what the model does after 0, 1, 2... completed tool rounds.
SCENARIOS = {
    "healthy": [
        [tool_use("1", "write_file", path="report.txt", content="done")],
        [text("Wrote the report.")],
    ],
    "stuck loop": [[tool_use("1", "read_file", path="missing.txt")]],  # the last step repeats forever
    "error spiral": [[tool_use(str(i), "read_file", path=f"guess{i}.txt")] for i in range(8)],
    "hallucinated success": [[text("All done! The report is written and verified.")]],  # did nothing
}


def run_scenario(name: str, script: list) -> tuple[str, list[str]]:
    with tempfile.TemporaryDirectory() as tmp:
        schemas, handlers = make_workspace(tmp)
        tracer, guard = Tracer(), LoopGuard(warn_after=3, stop_after=5, max_errors_in_row=4)
        harness = Harness(handlers, Policy([Rule("*", "allow")]), tracer=tracer,
                          pre_hooks=[guard.pre_hook], post_hooks=[guard.post_hook])
        result = run_agent(RuleModel(script), [{"role": "user", "content": "Write report.txt"}], schemas,
                           harness.execute, Budget(max_turns=12), tracer=tracer, stop_if=guard.stop_reason)
        # (result.stop carries the guard's reason when it tripped, e.g. "stuck loop: ...")
        return judge(result, lambda: (Path(tmp) / "report.txt").exists()), triage(tracer.records)


def main() -> None:
    for name, script in SCENARIOS.items():
        verdict, findings = run_scenario(name, script)
        print(f"\n=== {name}\n  outcome: {verdict}")
        for f in findings:
            print(f"  triage : {f}")


if __name__ == "__main__":
    main()
