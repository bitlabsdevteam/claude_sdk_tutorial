"""5.1 Prompt chaining: fixed steps, each feeding the next, with a code gate between them.

Use when: the task splits cleanly into ordered steps and each step is easier on its own.
Don't use when: one prompt already does the job (a chain just adds latency and cost), or the steps
can't be known in advance (that is an agent).
"""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.budget import Budget
from common.config import make_client
from common.llm import LLMError, ask

BULLET_PREFIXES = ("-", "*", "•")


@dataclass
class ChainResult:
    ok: bool
    outline: str
    draft: str
    reason: str = ""


def check_outline(outline: str) -> str | None:
    """The gate: plain code, not another model call. Returns a failure reason or None."""
    bullets = [ln for ln in outline.splitlines() if ln.strip().startswith(BULLET_PREFIXES)]
    return None if len(bullets) == 3 else f"expected 3 bullets, got {len(bullets)}"


def run_chain(client, topic: str, budget: Budget) -> ChainResult:
    outline = ask(client, f"Write a 3-bullet outline for a short blog post about: {topic}. Bullets only.", budget=budget)
    # Gate: fail fast BEFORE paying for step 2 if step 1's output is unusable.
    if (problem := check_outline(outline)):
        return ChainResult(False, outline, "", f"gate failed: {problem}")
    draft = ask(client, f"Write a 90-word blog post that follows this outline exactly:\n{outline}", budget=budget)
    return ChainResult(True, outline, draft)


def main() -> None:
    budget = Budget(max_turns=4, max_total_tokens=10_000, max_cost_usd=0.10, timeout_s=60)
    try:
        result = run_chain(make_client(), "why agents need budgets", budget)
    except LLMError as e:
        sys.exit(f"[stopped] {e}")
    print(result.outline, "\n---\n", result.draft or result.reason)
    print(f"[cost] {budget.turns} calls, ~${budget.cost_usd:.4f}")


if __name__ == "__main__":
    main()
