"""4.2 A minimal MCP server: two read-only tools over stdio.

Run it directly only to see it wait for input; normally a client launches it as a subprocess.
Inspect it with:  npx @modelcontextprotocol/inspector .venv/bin/python 04_mcp/server_basic/server.py
"""
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # make `common` importable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from common import demo_tools

mcp = MCPServer("demo-tools")

# Both tools only read data, so say so: clients can use the hint to skip approval prompts.
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False)


# The docstring becomes the tool description and the type hints become the input schema,
# so they are the whole interface the model sees (same rules as 02_tools/tool_design.md).
@mcp.tool(annotations=READ_ONLY)
def get_weather(location: str, unit: Literal["celsius", "fahrenheit"] = "celsius") -> str:
    """Get the current weather for one city (not a forecast)."""
    try:
        return demo_tools.get_weather(location, unit)
    except demo_tools.ToolError as e:
        # An unexpected exception is reported to the client with a generic message.
        # Raising ToolError keeps OUR message, so the model gets the recovery hint.
        raise ToolError(str(e)) from e


@mcp.tool(annotations=READ_ONLY)
def calculate(expression: str) -> str:
    """Evaluate an arithmetic expression using + - * / ** and numbers."""
    try:
        return demo_tools.calculate(expression)
    except demo_tools.ToolError as e:
        raise ToolError(str(e)) from e


if __name__ == "__main__":
    # stdio: the client owns our stdin/stdout, so never print() to stdout here (it would corrupt the protocol).
    mcp.run("stdio")
