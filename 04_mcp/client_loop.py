"""4.3 An MCP client inside your own agent loop: list tools, translate, call, return results.

The agent loop is the bounded `run_agent` from 03_agents; MCP only replaces where the tools come from.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded loop from Level 3

from agent import run_agent
from mcp import Client, StdioServerParameters

from common.budget import Budget
from common.config import make_client

MAX_RESULT_CHARS = 4_000  # tool output is untrusted and can be huge; cap it explicitly


class McpToolBridge:
    """Adapts an MCP `Client` to the two things an agent loop needs: API tool definitions and an executor."""

    def __init__(self, client: Client, allowed: set[str], max_chars: int = MAX_RESULT_CHARS):
        self.client, self.allowed, self.max_chars = client, allowed, max_chars

    async def api_tools(self) -> list[dict]:
        tools, cursor = [], None
        while True:  # tool lists can be paginated
            page = await self.client.list_tools(cursor=cursor)
            tools += page.tools
            cursor = page.next_cursor
            if not cursor:
                break
        # Allowlist: only expose tools we chose, so a server that adds a dangerous tool later gets ignored.
        # MCP and the Messages API use nearly the same shape: only the schema key name differs.
        return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
                for t in tools if t.name in self.allowed]

    async def call(self, name: str, arguments: dict) -> tuple[str, bool]:
        if name not in self.allowed:  # defense in depth: re-check at call time
            return f"Tool '{name}' is not allowed. Allowed: {', '.join(sorted(self.allowed))}.", True
        result = await self.client.call_tool(name, arguments)
        parts = [c.text if c.type == "text" else f"[{c.type} content omitted]" for c in result.content]
        text = "\n".join(parts)
        if len(text) > self.max_chars:  # never truncate silently: tell the model it was cut
            text = text[:self.max_chars] + f"\n[truncated: {len(text) - self.max_chars} more chars]"
        return text, bool(result.is_error)  # is_error maps straight onto the tool_result field


async def run_with_mcp(api_client, bridge: McpToolBridge, task: str, budget: Budget):
    tools = await bridge.api_tools()
    loop = asyncio.get_running_loop()

    def execute(name: str, tool_input: dict) -> tuple[str, bool]:
        # run_agent is synchronous and runs in a worker thread; hop back to the event loop,
        # which owns the MCP connection, to make the async call.
        return asyncio.run_coroutine_threadsafe(bridge.call(name, tool_input), loop).result()

    return await asyncio.to_thread(
        run_agent, api_client, [{"role": "user", "content": task}], tools, execute, budget,
    )


async def main() -> None:
    server = StdioServerParameters(command=sys.executable, args=[str(ROOT / "04_mcp/server_basic/server.py")])
    async with Client(server) as mcp_client:  # starts the server subprocess and handshakes
        bridge = McpToolBridge(mcp_client, allowed={"get_weather", "calculate"})
        budget = Budget(max_turns=6, max_total_tokens=40_000, max_cost_usd=0.25, timeout_s=90)
        result = await run_with_mcp(make_client(), bridge, "What is the weather in Tokyo, and what is 12 * 12?", budget)
        print(f"[stop] {result.stop} | turns={budget.turns} cost~${budget.cost_usd:.4f}")
        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
