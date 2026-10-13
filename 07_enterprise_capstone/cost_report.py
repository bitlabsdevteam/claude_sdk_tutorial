"""7.8 Cost per COMPLETED task, not per request: failed and denied runs still cost money.

Runs the offline evals and reports spend with the Level 6 Ledger. Numbers are scripted-token estimates here;
point it at `--live` eval results for real figures.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "06_harness", ROOT / "07_enterprise_capstone"):
    sys.path.insert(0, str(p))

from budgets import Ledger
from run_evals import load_cases, run_case

from common.budget import Budget


def main() -> None:
    ledger = Ledger(daily_cap_usd=5.0)
    for case in load_cases():
        r = run_case(case)
        b = Budget()
        b.cost_usd, b.turns = r["cost_usd"], 1
        ledger.record(case["id"], b, completed=r["passed"])
    print(f"tasks={len(ledger.tasks)} completed={ledger.completed} total=${ledger.total:.4f} wasted=${ledger.wasted:.4f}")
    print(f"cost per completed task: ${ledger.cost_per_completed():.4f}")


if __name__ == "__main__":
    main()
