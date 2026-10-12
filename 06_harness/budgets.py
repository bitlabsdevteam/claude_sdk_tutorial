"""6.11 Budgets, effort tuning, and cost ceilings: measure cost per COMPLETED TASK, not per request.

A cheap request that needs five retries is not cheap, and a failed task still cost money. So: track spend per
task, count only completed tasks in the denominator's value, and stop starting new work past a ceiling.

Two different budgets, do not confuse them:
  Budget (common/budget.py)  - HARD, enforced by your harness; the loop stops.
  task_budget (API, beta)    - ADVISORY, the model sees a token countdown and paces itself to finish gracefully.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.budget import Budget
from common.config import MODEL, make_client

# Set effort EXPLICITLY per task type. Opus 5.5 defaults to "medium"; the right level is measured, not guessed
# (6.19). Lower effort for simple, high-volume work; raise it only where a quality eval shows it pays.
EFFORT_FOR = {"classify": "low", "extract": "low", "summarize": "low", "support_reply": "medium",
              "code_review": "high", "agentic_coding": "xhigh"}
MIN_TASK_BUDGET = 20_000  # the API rejects smaller task budgets


def effort_for(task_type: str) -> str:
    return EFFORT_FOR.get(task_type, "medium")


def task_budget_kwargs(total: int, effort: str = "high") -> dict:
    """Extra args for `client.beta.messages.stream(...)` (streaming, since the output can be large)."""
    if total < MIN_TASK_BUDGET:
        raise ValueError(f"task budget must be at least {MIN_TASK_BUDGET:,} tokens")
    return {"betas": ["task-budgets-2026-03-13"],
            "output_config": {"effort": effort, "task_budget": {"type": "tokens", "total": total}}}


@dataclass
class TaskRecord:
    task_id: str
    cost_usd: float
    requests: int
    completed: bool


@dataclass
class Ledger:
    daily_cap_usd: float
    tasks: list[TaskRecord] = field(default_factory=list)

    def record(self, task_id: str, budget: Budget, completed: bool) -> None:
        self.tasks.append(TaskRecord(task_id, budget.cost_usd, budget.turns, completed))

    @property
    def total(self) -> float:
        return sum(t.cost_usd for t in self.tasks)

    @property
    def completed(self) -> int:
        return sum(t.completed for t in self.tasks)

    @property
    def wasted(self) -> float:
        return sum(t.cost_usd for t in self.tasks if not t.completed)

    def cost_per_completed(self) -> float | None:
        # ALL spend, including failed tasks, divided by tasks that actually delivered.
        return self.total / self.completed if self.completed else None

    def cost_per_request(self) -> float:
        reqs = sum(t.requests for t in self.tasks)
        return self.total / reqs if reqs else 0.0

    def can_start(self) -> tuple[bool, str]:
        if self.total >= self.daily_cap_usd:
            return False, f"daily cap ${self.daily_cap_usd:.2f} reached (spent ${self.total:.2f})"
        return True, "ok"


def main() -> None:
    ledger = Ledger(daily_cap_usd=1.00)
    runs = [("t1", 0.10, 4, True), ("t2", 0.12, 5, True), ("t3", 0.40, 12, False), ("t4", 0.11, 4, True)]
    for task_id, cost, turns, ok in runs:
        allowed, why = ledger.can_start()
        if not allowed:
            print(f"{task_id}: refused to start: {why}")
            continue
        ledger.record(task_id, Budget(cost_usd=cost, turns=turns), ok)
    print(f"tasks={len(ledger.tasks)} completed={ledger.completed} total=${ledger.total:.2f} wasted=${ledger.wasted:.2f}")
    print(f"cost per REQUEST        : ${ledger.cost_per_request():.3f}   <- looks cheap")
    print(f"cost per COMPLETED task : ${ledger.cost_per_completed():.3f}   <- what you actually pay for results")
    ledger.record("t5", Budget(cost_usd=0.5, turns=9), False)
    print("after more spend:", ledger.can_start())
    print("\neffort by task type:", {k: effort_for(k) for k in [*EFFORT_FOR, "unknown_new_task"]})
    print("task_budget request args:", task_budget_kwargs(30_000))
    if "--live" in sys.argv:  # paid; the budget is advisory, so this only shows the request is accepted
        with make_client().beta.messages.stream(
            model=MODEL, max_tokens=8_000, messages=[{"role": "user", "content": "List three tips for testing agents."}],
            **task_budget_kwargs(MIN_TASK_BUDGET, effort_for("summarize")),
        ) as stream:
            final = stream.get_final_message()
        print(f"live: stop={final.stop_reason} in={final.usage.input_tokens} out={final.usage.output_tokens}")


if __name__ == "__main__":
    main()
