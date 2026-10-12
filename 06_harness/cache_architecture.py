"""6.4 Cache-friendly prompt architecture: stable prefix first, volatile content last, append don't edit.

The cache matches a PREFIX in the order tools -> system -> messages, so one changed byte early invalidates
everything after it. Put what never changes first; put what changes (time, user state, per-turn reminders)
at the END, as appended messages, never inside `system`.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the prefix comparison from 6.3

from append_only import violations

# Things that silently bust the cache when they appear in the stable prefix.
VOLATILE_PATTERNS = {
    "timestamp/date": re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2})?"),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    "request/session id": re.compile(r"\b(?:request|session|trace)[ _-]?id\b", re.I),
}


def with_volatile(messages: list, note: str) -> list:
    """Append changing context as a trailing system message (supported on Opus 5.5 / Sonnet 5.5, no beta header).
    It must follow a user message. Earlier ones stay in place, so the prefix before it never changes."""
    if not messages or messages[-1]["role"] != "user":
        raise ValueError("a mid-conversation system message must follow a user message")
    return [*messages, {"role": "system", "content": note}]


def audit_system(system: str) -> list[str]:
    """Static check: does the supposedly stable prompt contain anything that changes?"""
    return [f"{name}: {m.group(0)!r}" for name, rx in VOLATILE_PATTERNS.items() if (m := rx.search(system))]


def build_request(stable_system: str, tools: list, history: list, volatile_note: str | None = None) -> dict:
    messages = with_volatile(history, volatile_note) if volatile_note else list(history)
    return {"system": stable_system, "tools": tools, "messages": messages}


def main() -> None:
    stable = "You are a support assistant. Follow the refund policy in the handbook."
    bad = f"{stable} Current time: 2026-10-12T09:15. Session id: abc"
    print("audit bad prompt :", audit_system(bad))
    print("audit good prompt:", audit_system(stable) or "clean")

    # Turn 1 and turn 2 of a good design: the time lives in an appended message, the prefix is untouched.
    h1 = [{"role": "user", "content": "Where is my order?"}]
    turn1 = build_request(stable, [], h1, "It is 09:15 UTC.")
    h2 = [*h1, {"role": "assistant", "content": "Checking."}, {"role": "user", "content": "Any update?"}]
    turn2 = build_request(stable, [], h2, "It is 09:20 UTC.")
    # The turn-1 volatile note is dropped from our rebuilt history here to show the pitfall:
    print("rebuilt-from-scratch history:", violations(turn1, turn2) or "prefix intact")
    # Right way: keep the ORIGINAL appended note in the stored history and append the next one after it.
    stored = [*turn1["messages"], {"role": "assistant", "content": "Checking."}, {"role": "user", "content": "Any update?"}]
    turn2_ok = build_request(stable, [], stored, "It is 09:20 UTC.")
    print("append-only history       :", violations(turn1, turn2_ok) or "prefix intact")


if __name__ == "__main__":
    main()
