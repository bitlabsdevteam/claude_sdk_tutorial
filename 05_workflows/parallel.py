"""5.3 Parallelization: sectioning (independent parts at once) and voting (same task N times).

Use sectioning when: sub-tasks are independent, so running them together cuts latency.
Use voting when: one answer is unreliable and a majority is worth N times the cost.
Don't use when: steps depend on each other, or cost matters more than latency/confidence.
"""
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from pydantic import BaseModel

from common.budget import Budget
from common.config import make_client
from common.llm import LLMError, ask

MAX_WORKERS = 4  # bound concurrency: protects rate limits and keeps spend predictable


def _run_all(fns: list) -> list:
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        return list(pool.map(lambda f: f(), fns))  # map preserves order


def sectioning(client, code: str, budget: Budget) -> dict[str, str | None]:
    """Review the same code from three independent angles at the same time."""
    aspects = ["security", "performance", "readability"]

    def review(aspect: str):
        try:
            return ask(client, f"Review this code for {aspect} only. Max 2 sentences.\n\n{code}", budget=budget)
        except LLMError:
            return None  # one failed branch shouldn't discard the others; the caller sees the gap

    return dict(zip(aspects, _run_all([lambda a=a: review(a) for a in aspects])))


class Verdict(BaseModel):
    safe: Literal["yes", "no"]


def voting(client, text: str, budget: Budget, n: int = 3) -> tuple[str, Counter]:
    """Ask the same yes/no question n times and take the majority (use an odd n)."""

    def vote():
        try:
            return ask(client, f"Is this message safe to auto-approve? Answer yes or no.\n\n{text}",
                       schema=Verdict, budget=budget, max_tokens=50).safe
        except LLMError:
            return None

    tally = Counter(v for v in _run_all([vote] * n) if v)
    if not tally:
        raise LLMError("no valid votes")
    return tally.most_common(1)[0][0], tally


def main() -> None:
    budget = Budget(max_turns=10, max_total_tokens=30_000, max_cost_usd=0.20, timeout_s=90)
    client = make_client()
    code = "def get(u):\n    import os\n    return os.popen('curl ' + u).read()\n"
    for aspect, review in sectioning(client, code, budget).items():
        print(f"[{aspect}] {review}")
    print("vote:", voting(client, "Please wire $9,000 to this new account today.", budget))
    print(f"[cost] {budget.turns} calls, ~${budget.cost_usd:.4f}")


if __name__ == "__main__":
    main()
