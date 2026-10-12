"""6.5 Just-in-time context and progressive disclosure: load detail only when the model asks for it.

Up-front loading puts everything in every request (and re-bills it each turn). Progressive disclosure
(the "skills" pattern) keeps a tiny catalog in context and gives the model a tool to load one topic in
full when it needs it. Use up-front only when the data is small and almost always needed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded loop from Level 3

from common.budget import Budget
from common.config import make_client
from common.context import approx_tokens

MAX_TOPIC_CHARS = 6_000


def catalog() -> dict[str, str]:
    """topic name -> one-line description (the heading of each level's README)."""
    out = {}
    for readme in sorted(ROOT.glob("0*_*/README.md")):
        first = readme.read_text().splitlines()[0].lstrip("# ").strip()
        out[readme.parent.name] = first
    return out


def list_topics() -> str:
    return "\n".join(f"{name}: {desc}" for name, desc in catalog().items())


def load_topic(name: str) -> str:
    if name not in catalog():  # the model controls `name`: only catalog entries are loadable
        raise KeyError(f"Unknown topic '{name}'. Call list_topics first.")
    text = (ROOT / name / "README.md").read_text()
    if len(text) > MAX_TOPIC_CHARS:  # say so; never cut silently
        return text[:MAX_TOPIC_CHARS] + f"\n[truncated: {len(text) - MAX_TOPIC_CHARS} more chars]"
    return text


def upfront_text() -> str:
    return "\n\n".join(load_topic(n) for n in catalog())


def execute(name: str, tool_input: dict) -> tuple[str, bool]:
    try:
        if name == "list_topics":
            return list_topics(), False
        if name == "load_topic":
            return load_topic(tool_input["name"]), False
        return f"Unknown tool '{name}'.", True
    except KeyError as e:
        return str(e.args[0]), True


def _tool(name: str, desc: str, props: dict) -> dict:
    return {"name": name, "description": desc, "strict": True, "input_schema": {
        "type": "object", "properties": props, "required": list(props), "additionalProperties": False}}


TOOLS = [
    _tool("list_topics", "List the available topics with one-line descriptions. Call this first.", {}),
    _tool("load_topic", "Load the full text of one topic from list_topics.", {"name": {"type": "string"}}),
]


def main() -> None:
    from agent import run_agent

    up, index = approx_tokens(upfront_text()), approx_tokens(list_topics())
    print(f"up-front: ~{up:,} tokens on EVERY request | catalog only: ~{index:,} tokens (+ topics loaded on demand)")
    budget = Budget(max_turns=6, max_total_tokens=40_000, max_cost_usd=0.20, timeout_s=90)
    result = run_agent(make_client(), [{"role": "user", "content": "What does the MCP level teach about security?"}],
                       TOOLS, execute, budget, "Answer from the repo topics. List topics, then load only what you need.")
    print(f"[stop] {result.stop} | turns={budget.turns}\n{result.text}")


if __name__ == "__main__":
    main()
