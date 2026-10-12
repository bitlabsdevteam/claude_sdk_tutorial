"""5.5 Evaluator-optimizer: generate, critique against a rubric, refine, repeat.

Use when: you have clear criteria and a first draft is measurably improved by feedback.
Don't use when: there is no clear rubric (the critic just adds noise), or one pass is already good enough.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from pydantic import BaseModel

from common.budget import Budget
from common.config import make_client
from common.llm import LLMError, ask

MAX_ROUNDS = 3  # the loop MUST be bounded: a picky critic would otherwise never say "pass"
RUBRIC = "Exactly two sentences. Mentions a concrete example. No jargon. Under 50 words."


class Critique(BaseModel):
    passed: bool
    feedback: str  # specific, actionable changes; empty if passed


@dataclass
class Outcome:
    draft: str
    rounds: int
    converged: bool  # False means we stopped at MAX_ROUNDS, not because the critic was satisfied


def run(client, task: str, budget: Budget, max_rounds: int = MAX_ROUNDS) -> Outcome:
    draft = ask(client, task, budget=budget)
    for round_no in range(1, max_rounds + 1):
        critique = ask(
            client, f"Rubric: {RUBRIC}\n\nDraft:\n{draft}\n\nDoes the draft meet EVERY rubric item?",
            schema=Critique, budget=budget, max_tokens=300,
        )
        if critique.passed:
            return Outcome(draft, round_no, True)
        if round_no == max_rounds:
            break  # don't pay for a refinement we'd never critique
        draft = ask(client, f"Task: {task}\nRubric: {RUBRIC}\nCurrent draft:\n{draft}\n"
                            f"Feedback:\n{critique.feedback}\nRewrite the draft to fix the feedback.", budget=budget)
    return Outcome(draft, max_rounds, False)


def main() -> None:
    budget = Budget(max_turns=8, max_total_tokens=20_000, max_cost_usd=0.15, timeout_s=90)
    try:
        out = run(make_client(), "Explain what a bounded agent loop is.", budget)
    except LLMError as e:
        sys.exit(f"[stopped] {e}")
    print(out.draft)
    print(f"[rounds={out.rounds} converged={out.converged}] ~${budget.cost_usd:.4f}")


if __name__ == "__main__":
    main()
