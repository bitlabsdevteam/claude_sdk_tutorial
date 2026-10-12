"""3.7 Long conversations: context editing (clear old tool results) vs compaction (summarize).

Both are beta. Editing is cheap and lossy-by-deletion; compaction keeps a summary. Usage: python 03_agents/long_context.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, make_client

EDITING_BETA = "context-management-2025-06-27"
COMPACTION_BETA = "compact-2026-01-12"

# Tunable. If the API rejects a low trigger (400), raise it.
TRIGGER_TOKENS, KEEP_TOOL_USES = 6_000, 2


def editing_config() -> dict:
    # Clears the oldest tool results once input passes the trigger, keeping the last few tool uses.
    return {"edits": [{
        "type": "clear_tool_uses_20250919",
        "trigger": {"type": "input_tokens", "value": TRIGGER_TOKENS},
        "keep": {"type": "tool_uses", "value": KEEP_TOOL_USES},
    }]}


def compaction_config() -> dict:
    # Summarizes earlier context into a compaction block. You MUST append response.content (not just text)
    # to history so the block is passed back on the next request.
    return {"edits": [{"type": "compact_20260112"}]}


LOG_TOOL = {
    "name": "get_log_chunk", "description": "Return log chunk n (1-8). Each chunk is large.", "strict": True,
    "input_schema": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"],
                     "additionalProperties": False},
}


def execute(name: str, tool_input: dict) -> tuple[str, bool]:
    if name != "get_log_chunk":
        return f"Unknown tool '{name}'.", True
    n = tool_input["n"]
    return " ".join(f"[chunk {n}] line {i}: heartbeat ok" for i in range(400)), False


def main() -> None:
    client = make_client()
    messages = [{"role": "user", "content": "Fetch log chunks 1 through 5, one per call, and tell me if any contain errors."}]
    for turn in range(1, 9):  # bounded
        response = client.beta.messages.create(
            model=MODEL, max_tokens=2048, betas=[EDITING_BETA], tools=[LOG_TOOL], messages=messages,
            context_management=editing_config(), output_config={"effort": "low"},
        )
        applied = response.context_management.applied_edits if response.context_management else []
        print(f"turn {turn}: input_tokens={response.usage.input_tokens} stop={response.stop_reason} "
              f"edits_applied={[(e.type, getattr(e, 'cleared_tool_uses', None)) for e in applied]}")
        messages.append({"role": "assistant", "content": response.content})  # history stays append-only
        if response.stop_reason != "tool_use":
            print("".join(b.text for b in response.content if b.type == "text"))
            return
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id, "is_error": err, "content": out}
            for b in response.content if b.type == "tool_use"
            for out, err in [execute(b.name, b.input)]
        ]})
    print("[stop] max turns")


if __name__ == "__main__":
    main()
