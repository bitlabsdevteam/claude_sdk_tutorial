"""5.6 Subagents: each gets a fresh, isolated context and hands back ONLY a small typed summary.

Use when: a sub-task needs lots of reading/tool output that would bloat the parent's context.
Don't use when: the sub-task is small (the handoff costs more than it saves), or the parent needs the
raw detail (then keep it in one context).
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded agent loop and its read-only tools

import research_agent
from agent import run_agent
from pydantic import BaseModel, Field

from common.budget import Budget
from common.config import make_client
from common.llm import LLMError, ask


class Handoff(BaseModel):
    """The contract between a subagent and its parent: short, structured, nothing else crosses over."""
    summary: str = Field(max_length=500)
    sources: list[str] = Field(default_factory=list, description="File paths the answer is based on.")


def run_subagent(client, question: str, budget: Budget) -> Handoff:
    # A brand-new message list: the parent's history is NOT shared, and this one is discarded afterwards.
    sub_budget = Budget(max_turns=6, max_total_tokens=30_000, max_cost_usd=0.15, timeout_s=60)
    result = run_agent(client, [{"role": "user", "content": question}], research_agent.TOOLS,
                       research_agent.execute, sub_budget, research_agent.SYSTEM)
    # Fold the subagent's spend into the parent's budget so cost is tracked per completed task.
    budget.absorb(sub_budget)
    if result.stop != "done":
        raise LLMError(f"subagent stopped early: {result.stop}")
    # Compress the transcript into the typed handoff; the raw tool output stays behind.
    return ask(client, f"Question: {question}\nFindings:\n{result.text}\nFill in the handoff.",
               schema=Handoff, budget=budget, max_tokens=800)


def run(client, questions: list[str], budget: Budget) -> str:
    with ThreadPoolExecutor(max_workers=len(questions)) as pool:
        handoffs = list(pool.map(lambda q: run_subagent(client, q, budget), questions))
    # The parent only ever sees these short summaries.
    digest = "\n".join(f"- {q}\n  {h.summary} (sources: {', '.join(h.sources) or 'n/a'})"
                       for q, h in zip(questions, handoffs))
    return ask(client, f"Combine these findings into a 3-sentence answer:\n{digest}", budget=budget)


def main() -> None:
    budget = Budget(max_turns=30, max_total_tokens=150_000, max_cost_usd=0.60, timeout_s=180)
    questions = ["What does Level 2 of this repo teach?", "What does Level 3 of this repo teach?"]
    try:
        print(run(make_client(), questions, budget))
    except LLMError as e:
        sys.exit(f"[stopped] {e}")
    print(f"[cost] {budget.turns} calls, ~${budget.cost_usd:.4f}")


if __name__ == "__main__":
    main()
