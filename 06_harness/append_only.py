"""6.3 Append-only history and preserved thinking: never edit an earlier turn.

A thinking block is bound to the conversation that produced it (system prompt, tools, and every earlier
message). If you change any of those and send the block back, the API rejects it (400) on enforced accounts,
and the prompt cache misses either way. So: freeze `system`, declare all tools at the start, only append,
and return the assistant's content UNCHANGED (thinking blocks included).

This file is step 1 of the three-step check: compare consecutive request bodies offline.
Steps 2-3 (a live run with `prefix_mismatch_behavior`) are `binding_check_kwargs()` below.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.context import plain


def canon(obj):
    """Canonical form for comparing: sorted keys, SDK objects as dicts, cache_control markers ignored
    (adding, moving or removing them is allowed and does not count as an edit)."""
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k != "cache_control"}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    return json.dumps(strip(json.loads(json.dumps(obj, default=plain))), sort_keys=True)


def violations(prev: dict, nxt: dict) -> list[str]:
    """Problems between two consecutive request bodies ({'system', 'tools', 'messages'}). Empty list = OK."""
    found = []
    if canon(prev.get("system")) != canon(nxt.get("system")):
        found.append("system prompt changed: freeze it and append a role:'system' message instead")

    old = {t["name"]: canon(t) for t in prev.get("tools") or []}
    new = {t["name"]: (canon(t), t) for t in nxt.get("tools") or []}
    for name, c in old.items():  # reordering is fine: tools are compared as a name-keyed set
        if name not in new:
            found.append(f"tool '{name}' removed: send a tool_removal message instead")
        elif new[name][0] != c:
            found.append(f"tool '{name}' definition changed")
    for name, (_, t) in new.items():
        if name not in old and not t.get("defer_loading"):
            found.append(f"tool '{name}' added mid-session: declare it up front with defer_loading")

    pm, nm = prev.get("messages") or [], nxt.get("messages") or []
    if len(nm) < len(pm):
        found.append(f"history shortened ({len(pm)} -> {len(nm)} messages): use context editing or compaction")
    for i, (a, b) in enumerate(zip(pm, nm)):
        if canon(a) != canon(b):
            found.append(f"message {i} was edited: append, never rewrite")
    return found


def check_session(requests: list[dict]) -> list[tuple[int, list[str]]]:
    """Every consecutive pair, e.g. captured from a few normal turns. Returns (turn_index, problems)."""
    return [(i, v) for i in range(1, len(requests)) if (v := violations(requests[i - 1], requests[i]))]


def binding_check_kwargs(mode: str = "error") -> dict:
    """Step 2: extra request kwargs for a live multi-turn run (use client.beta.messages.create).
    Setting the field opts ANY account into enforcement, so edits show up as 400s ("error", good for CI)
    or as `input_transformations` entries ("drop_block"). Only valid with adaptive thinking."""
    assert mode in {"error", "drop_block"}
    return {
        "betas": ["thinking-binding-controls-2026-08-01"],
        "thinking": {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": mode}},
    }


def main() -> None:
    sys_prompt, tools = "You are a coding assistant.", [{"name": "run", "description": "d", "input_schema": {}}]
    t1 = {"system": sys_prompt, "tools": tools, "messages": [{"role": "user", "content": "hi"}]}
    reply = {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                                              {"type": "text", "text": "hello"}]}
    t2 = {**t1, "messages": [*t1["messages"], reply, {"role": "user", "content": "more"}]}
    reply2 = {"role": "assistant", "content": [{"type": "text", "text": "sure"}]}
    t3 = {**t2, "messages": [*t2["messages"], reply2, {"role": "user", "content": "and more"}]}
    # Bad edits made while building turn 3:
    bad_system = {**t3, "system": sys_prompt + " Today is 2026-10-12."}  # classic: a date in the prompt
    stripped = {"role": "assistant", "content": [{"type": "text", "text": "hello"}]}  # thinking block removed
    bad_trim = {**t3, "messages": [t3["messages"][0], stripped, *t3["messages"][2:]]}
    bad_tool = {**t3, "tools": []}

    print(f"{'append-only':>18}: {violations(t1, t2) or 'OK'}")
    print(f"{'append-only (t2>t3)':>18}: {violations(t2, t3) or 'OK'}")
    for name, nxt in [("system edited", bad_system), ("thinking stripped", bad_trim), ("tool removed", bad_tool)]:
        print(f"{name:>18}: {violations(t2, nxt)}")


if __name__ == "__main__":
    main()
