"""5.4 Orchestrator-workers: a lead model decides the sub-tasks at run time, workers do them, the lead merges.

Use when: you can't know the sub-tasks up front (they depend on the input) but each is self-contained.
Don't use when: the sub-tasks are fixed (use sectioning in 5.3), or they depend on each other's output.
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from pydantic import BaseModel, Field

from common.budget import Budget
from common.config import make_client
from common.llm import LLMError, ask

MAX_SUBTASKS = 4  # the lead decides the fan-out, so the harness caps it


class Plan(BaseModel):
    subtasks: list[str] = Field(description="Independent, self-contained sub-tasks.")


def run(client, goal: str, budget: Budget) -> str:
    plan = ask(client, f"Break this goal into at most {MAX_SUBTASKS} independent sub-tasks:\n{goal}",
               schema=Plan, budget=budget, max_tokens=500)
    subtasks = plan.subtasks[:MAX_SUBTASKS]
    if len(plan.subtasks) > MAX_SUBTASKS:  # never drop work silently
        print(f"[orchestrator] lead proposed {len(plan.subtasks)} sub-tasks; running the first {MAX_SUBTASKS}")
    if not subtasks:
        raise LLMError("lead returned no sub-tasks")

    def work(task: str) -> str:
        # Workers see only their sub-task, not the whole conversation: small, cheap, focused contexts.
        return ask(client, f"Complete this sub-task in 2-3 sentences:\n{task}", budget=budget)

    with ThreadPoolExecutor(max_workers=MAX_SUBTASKS) as pool:
        results = list(pool.map(work, subtasks))

    findings = "\n".join(f"- {t}: {r}" for t, r in zip(subtasks, results))
    return ask(client, f"Goal: {goal}\nWorker findings:\n{findings}\nWrite a short combined answer.", budget=budget)


def main() -> None:
    budget = Budget(max_turns=10, max_total_tokens=40_000, max_cost_usd=0.30, timeout_s=120)
    try:
        print(run(make_client(), "Plan a one-day team offsite for 12 people in a city of your choice.", budget))
    except LLMError as e:
        sys.exit(f"[stopped] {e}")
    print(f"[cost] {budget.turns} calls, ~${budget.cost_usd:.4f}")


if __name__ == "__main__":
    main()
