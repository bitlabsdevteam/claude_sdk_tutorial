"""4.7 Tool search: with many tools, defer their definitions and let the model search for what it needs.

Tool definitions are sent (and billed) on every request. With dozens of MCP tools that dominates the prompt.
Marking tools `defer_loading: true` keeps them out of context until the search tool surfaces them.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded loop from Level 3

from agent import run_agent

from common.budget import Budget
from common.config import make_client

DOMAINS = ["customer", "invoice", "ticket", "shipment", "product", "employee"]
VERBS = ["get", "list", "create", "cancel", "export"]


def build_tools(defer: bool = True) -> list[dict]:
    tools = [{
        "name": f"{d}_{v}",
        "description": f"{v.capitalize()} {d} records in the demo back office system.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": [],
                         "additionalProperties": False},
        **({"defer_loading": True} if defer else {}),
    } for d in DOMAINS for v in VERBS]
    # The search tool itself must NOT be deferred, and at least one tool must stay non-deferred.
    tools.append({"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"})
    return tools


def execute(name: str, tool_input: dict) -> tuple[str, bool]:
    return f"(demo) {name} called with {tool_input}", False  # stand-in for a real MCP call


def main() -> None:
    budget = Budget(max_turns=6, max_total_tokens=60_000, max_cost_usd=0.30, timeout_s=90)
    task = "Find and use the right tool to get the invoice with id INV-7."
    result = run_agent(make_client(), [{"role": "user", "content": task}], build_tools(), execute, budget)
    print(f"[stop] {result.stop} | turns={budget.turns}")
    print(result.text)
    # Compare: run with build_tools(defer=False) and look at the `in=` tokens of the first turn.


if __name__ == "__main__":
    main()
