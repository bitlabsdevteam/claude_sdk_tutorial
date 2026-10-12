"""5.7 Model routing: use the cheapest model that is good enough, and optionally pair with an advisor.

Use when: your traffic mixes easy and hard requests, and the cheap model handles the easy ones well.
Don't use when: you haven't measured it. Try the best model at LOW effort first: one model keeps one cache
and often matches a cheaper model's quality (see the claude-api cost guide). Routing mistakes cost quality.
"""
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from pydantic import BaseModel

from common.budget import Budget
from common.config import make_client
from common.llm import LLMError, ask

# The only place the cheaper models are used on purpose (CLAUDE.md: model routing examples).
MODEL_FOR = {"easy": "claude-haiku-5-5", "medium": "claude-sonnet-5-5", "hard": "claude-opus-5-5"}
ROUTER_MODEL = "claude-haiku-5-5"  # classifying is cheap, so the router itself is the cheapest model

ADVISOR_BETA = "advisor-tool-2026-03-01"


class Difficulty(BaseModel):
    level: Literal["easy", "medium", "hard"]


def routed_answer(client, question: str, budget: Budget) -> tuple[str, str]:
    level = ask(client, f"Rate how hard this question is to answer well:\n{question}", schema=Difficulty,
                model=ROUTER_MODEL, budget=budget, max_tokens=50).level
    return MODEL_FOR[level], ask(client, question, model=MODEL_FOR[level], budget=budget)


def advisor_answer(client, task: str) -> None:
    """Executor (Sonnet) does the work and can consult a stronger advisor (Opus) mid-task."""
    response = client.beta.messages.create(
        model="claude-sonnet-5-5", max_tokens=2048, betas=[ADVISOR_BETA],
        tools=[{"type": "advisor_20260301", "name": "advisor", "model": "claude-opus-5-5", "max_uses": 2}],
        # Forced tool_choice is rejected on current models, so nudge it from the prompt instead.
        messages=[{"role": "user", "content": f"{task}\nConsult your advisor once before answering."}],
    )
    if response.stop_reason == "refusal":
        print("Refused:", response.stop_details)
        return
    for block in response.content:
        if block.type == "advisor_tool_result":
            # The payload shape depends on the advisor model: switch on content.type, not the block type.
            kind = block.content.type  # advisor_result | advisor_redacted_result | advisor_tool_result_error
            print(f"[advisor] {kind}" + (" (encrypted: replayable, not readable)" if "redacted" in kind else ""))
        elif block.type == "text":
            print(block.text)


def main() -> None:
    budget = Budget(max_turns=6, max_total_tokens=20_000, max_cost_usd=0.15, timeout_s=90)
    client = make_client()
    for q in ["What is 2 + 2?", "Design a retry policy for a payments API that avoids double charges."]:
        try:
            model, answer = routed_answer(client, q, budget)
        except LLMError as e:
            sys.exit(f"[stopped] {e}")
        print(f"[{model}] {answer[:200]}\n")
    print(f"[cost] {budget.turns} calls, ~${budget.cost_usd:.4f}")
    if "--advisor" in sys.argv:
        advisor_answer(client, "Give a 3-step plan for migrating a cron job to a queue worker.")


if __name__ == "__main__":
    main()
