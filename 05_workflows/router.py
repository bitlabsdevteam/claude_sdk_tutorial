"""5.2 Routing: classify the input, then dispatch to a specialised prompt.

Use when: inputs fall into distinct categories that need different prompts, tools, or models.
Don't use when: categories overlap heavily, or one good general prompt works (the classifier is extra
latency and a new way to be wrong).
"""
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from pydantic import BaseModel

from common.budget import Budget
from common.config import make_client
from common.llm import LLMError, ask


class Route(BaseModel):
    # A Literal makes the API constrain the label: the classifier cannot invent a category.
    category: Literal["billing", "technical", "general"]


HANDLERS = {
    "billing": "You are a billing support agent. Be precise about money, dates, and refund policy. Keep it short.",
    "technical": "You are a technical support engineer. Give numbered troubleshooting steps. Keep it short.",
    "general": "You are a friendly support agent. Answer briefly and offer further help.",
}


def route(client, message: str, budget: Budget) -> str:
    result = ask(client, f"Classify this customer message:\n{message}", schema=Route, budget=budget, max_tokens=100)
    # Defensive default: if routing ever returns something unexpected, fall back instead of crashing.
    return result.category if result.category in HANDLERS else "general"


def handle(client, message: str, budget: Budget) -> tuple[str, str]:
    category = route(client, message, budget)
    return category, ask(client, message, system=HANDLERS[category], budget=budget)


def main() -> None:
    budget = Budget(max_turns=8, max_total_tokens=20_000, max_cost_usd=0.15, timeout_s=60)
    client = make_client()
    for msg in ["I was charged twice this month.", "The app crashes when I open settings."]:
        try:
            category, reply = handle(client, msg, budget)
        except LLMError as e:
            sys.exit(f"[stopped] {e}")
        print(f"[{category}] {reply}\n")
    print(f"[cost] {budget.turns} calls, ~${budget.cost_usd:.4f}")


if __name__ == "__main__":
    main()
