"""6.2 Compaction: when history grows too big, replace it with a summary. Decide what to keep and what to drop.

Client-side "simple compaction": summarise the WHOLE conversation into one message and continue from
that alone (no earlier turns, no earlier thinking blocks, so nothing is tied to the old transcript).
Prefer server-side compaction or context editing when you can (see 03_agents/long_context.py); use this
when you need your own summarisation rules. Compaction resets the prompt cache, so do it rarely.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.budget import Budget
from common.config import make_client
from common.context import approx_tokens, block_type, blocks_of, plain
from common.llm import ask

KEEP = [
    "the user's goal and constraints",
    "decisions made and the reason for each",
    "exact names, IDs, file paths and values needed later",
    "open tasks and the very next step",
]
DROP = ["raw tool output (keep only its conclusion)", "dead ends and retries", "pleasantries"]


def needs_compaction(messages: list, threshold_tokens: int) -> bool:
    return approx_tokens(messages) >= threshold_tokens


def safe_to_compact(messages: list) -> bool:
    """Never compact in the middle of a tool round: a pending tool_use must keep its own history."""
    if not messages:
        return False
    last = messages[-1]
    kinds = [block_type(b) for b in blocks_of(last)]
    if last["role"] == "assistant":
        return "tool_use" not in kinds  # assistant is waiting for tool results
    return "tool_result" not in kinds  # user message that is just tool results = mid-round


def transcript_text(messages: list) -> str:
    return "\n".join(f"{m['role']}: {json.dumps(blocks_of(m), default=plain)}" for m in messages)


def compact(client, messages: list, budget: Budget) -> list:
    """Returns a one-message history. The caller appends the next user turn to it."""
    if not safe_to_compact(messages):
        raise ValueError("unsafe to compact: a tool round is still in progress")
    prompt = (
        "Summarise this conversation so work can continue from the summary alone.\n"
        f"KEEP: {'; '.join(KEEP)}.\nDROP: {'; '.join(DROP)}.\n\n"
        f"<conversation>\n{transcript_text(messages)}\n</conversation>"
    )
    # The full transcript goes to the summariser: we never silently cut the input (chunk it if too big).
    summary = ask(client, prompt, budget=budget, max_tokens=1500)
    return [{"role": "user", "content": f"<summary>\nSummary of the earlier conversation:\n{summary}\n</summary>"}]


def main() -> None:
    history = [
        {"role": "user", "content": "I'm migrating billing.py to Postgres; keep the public API stable."},
        {"role": "assistant", "content": "Plan: add a Repo class, keep charge() signature, migrate tables first."},
        {"role": "user", "content": "Decision: use psycopg3, not SQLAlchemy. Start with the invoices table."},
        {"role": "assistant", "content": "Done: created invoices table. Next: migrate payments table."},
    ]
    print(f"history ~{approx_tokens(history)} tokens; safe to compact: {safe_to_compact(history)}")
    budget = Budget(max_turns=2, max_total_tokens=10_000, max_cost_usd=0.05, timeout_s=60)
    new_history = compact(make_client(), history, budget)
    print(new_history[0]["content"])
    print(f"-> ~{approx_tokens(new_history)} tokens; cost ~${budget.cost_usd:.4f}")


if __name__ == "__main__":
    main()
