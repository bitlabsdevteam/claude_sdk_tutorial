"""3.4 State and memory: durable notes plus a resumable session, both on local disk.

Usage: python 03_agents/memory_agent.py <session-name> "<message>"
Run it twice with the same session name; the second run remembers the first.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable
sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the bounded loop from 3.2

from agent import run_agent

from common.budget import Budget
from common.config import make_client

STATE_DIR = Path(__file__).resolve().parents[1] / ".agent_state"  # git-ignored


def _name(session: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", session):  # no path tricks via the session name
        raise ValueError("session name must be letters, digits, _ or -")
    return session


def load_session(session: str) -> list:
    f = STATE_DIR / f"{_name(session)}.json"
    return json.loads(f.read_text()) if f.exists() else []


def save_session(session: str, messages: list) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    # SDK block objects -> plain dicts. Thinking blocks stay byte-for-byte as returned, so replay is valid.
    plain = [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else
              [b if isinstance(b, dict) else b.model_dump(mode="json", exclude_none=True) for b in m["content"]]}
             for m in messages]
    (STATE_DIR / f"{_name(session)}.json").write_text(json.dumps(plain, indent=2))


def notes_path() -> Path:
    return STATE_DIR / "notes.json"


def read_notes() -> dict:
    return json.loads(notes_path().read_text()) if notes_path().exists() else {}


def execute(name: str, tool_input: dict) -> tuple[str, bool]:
    """Memory tools: long-term facts that survive across sessions (unlike the message history)."""
    notes = read_notes()  # re-read each call so notes written by an earlier run are always seen
    if name == "remember":
        notes[tool_input["key"]] = tool_input["value"]
        STATE_DIR.mkdir(exist_ok=True)
        notes_path().write_text(json.dumps(notes, indent=2))
        return f"Remembered '{tool_input['key']}'.", False
    if name == "recall":
        return json.dumps(notes) if notes else "No notes saved yet.", False
    return f"Unknown tool '{name}'. Available: remember, recall.", True


TOOLS = [
    {"name": "remember", "description": "Save a durable fact about the user or task under a short key.",
     "strict": True, "input_schema": {"type": "object", "additionalProperties": False, "required": ["key", "value"],
                                      "properties": {"key": {"type": "string"}, "value": {"type": "string"}}}},
    {"name": "recall", "description": "Return all saved notes as JSON. Call at the start of a conversation.",
     "strict": True, "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
]
SYSTEM = "You have a persistent notebook. Call recall first, and remember durable facts the user shares."


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    session, user_msg = sys.argv[1], sys.argv[2]
    messages = load_session(session) + [{"role": "user", "content": user_msg}]
    budget = Budget(max_turns=6, max_total_tokens=40_000, max_cost_usd=0.20, timeout_s=60)
    result = run_agent(make_client(), messages, TOOLS, execute, budget, SYSTEM)
    save_session(session, result.messages)  # note: history grows each run; see 3.6/3.7 for managing it
    print(f"[stop] {result.stop}")
    print(result.text)


if __name__ == "__main__":
    main()
