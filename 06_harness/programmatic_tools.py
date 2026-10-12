"""6.7 Programmatic tool calling: Claude writes code that calls YOUR tools; only the final output returns to it.

Normal tool use: every call's result enters the model's context, then it reasons, then calls the next tool.
Programmatic: Claude writes a script (run in the code execution container) that calls your tool in a loop and
aggregates in code. Big intermediate results never touch the context, so tokens and round trips drop.
Use it for many calls or large results you will filter. Don't for strictly sequential, reasoning-heavy chains.

Rules from the docs (all handled below): the tool needs `allowed_callers`; NOT compatible with `strict`, forced
`tool_choice` or MCP-connector tools; the container id MUST be passed back while a call is pending; and the
message that answers programmatic calls may contain ONLY tool_result blocks. Paid run, budget-capped.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.budget import Budget
from common.config import MODEL, make_client

CODE_EXEC = {"type": "code_execution_20260120", "name": "code_execution"}
CALLER = "code_execution_20260120"
PRODUCTS = ["widget", "gadget", "gizmo", "doohickey", "thing"]
REGIONS = ["north", "south", "east"]

SALES_TOOL = {
    "name": "get_sales",
    "description": "Return ALL sales rows for one region as a JSON list of {product, units, price}. Large result.",
    "input_schema": {"type": "object", "properties": {"region": {"type": "string", "enum": REGIONS}},
                     "required": ["region"], "additionalProperties": False},
    "allowed_callers": [CALLER],  # makes it callable from code; no `strict` here (not supported with PTC)
}


def get_sales(region: str) -> str:
    if region not in REGIONS:
        raise ValueError(f"Unknown region '{region}'. Use one of: {', '.join(REGIONS)}.")
    rows = [{"product": PRODUCTS[i % 5], "units": (i * 7 + len(region)) % 13 + 1, "price": 10 + (i % 5) * 5}
            for i in range(300)]
    return json.dumps(rows)


def revenue(region: str) -> int:
    return sum(r["units"] * r["price"] for r in json.loads(get_sales(region)))


def execute(name: str, tool_input: dict) -> tuple[str, bool]:
    if name != "get_sales":
        return f"Unknown tool '{name}'.", True
    try:
        return get_sales(**tool_input), False
    except (ValueError, TypeError) as e:
        return str(e), True


def run(client, task: str, budget: Budget, max_turns: int = 8):
    """A manual loop: the container id and the tool-result-only rule need per-turn control."""
    messages, container, hidden_chars = [{"role": "user", "content": task}], None, 0
    for _ in range(max_turns):
        if (limit := budget.exceeded()):
            raise RuntimeError(f"budget exceeded: {limit}")
        kwargs = {"container": container} if container else {}
        response = client.messages.create(
            model=MODEL, max_tokens=4096, tools=[CODE_EXEC, SALES_TOOL], messages=messages,
            output_config={"effort": "low"}, **kwargs,
        )
        budget.record(response.usage, MODEL)
        if getattr(response, "container", None):
            container = response.container.id  # REQUIRED on the next request while a call is pending
        if response.stop_reason == "refusal":
            raise RuntimeError(f"refused: {response.stop_details}")
        messages.append({"role": "assistant", "content": response.content})  # unchanged, incl. server blocks
        if response.stop_reason == "pause_turn":
            continue  # server-side pause: just resume
        if response.stop_reason != "tool_use":
            return response, hidden_chars

        results = []
        for block in (b for b in response.content if b.type == "tool_use"):
            content, is_error = execute(block.name, block.input)
            caller = getattr(block.caller, "type", "direct")
            if caller != "direct":  # called from code: this output never enters the model's context
                hidden_chars += len(content)
            print(f"[tool] {block.name}({block.input}) via {caller}: {len(content):,} chars, error={is_error}")
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
        # ONLY tool_result blocks: any text here makes the API reject a programmatic continuation.
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"no final answer after {max_turns} turns")


def main() -> None:
    budget = Budget(max_turns=8, max_total_tokens=60_000, max_cost_usd=0.40, timeout_s=150)
    task = ("Using get_sales, compute total revenue (units * price) for the north, south and east regions, "
            "and say which is highest. Aggregate in code; do not print raw rows.")
    response, hidden = run(make_client(), task, budget)
    print("".join(b.text for b in response.content if b.type == "text"))
    print(f"[cost] {budget.turns} calls, ~${budget.cost_usd:.4f}, {hidden:,} chars of tool output kept out of context")
    print("expected:", {r: revenue(r) for r in REGIONS})


if __name__ == "__main__":
    main()
