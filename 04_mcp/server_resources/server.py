"""4.6 Beyond tools: resources (data the app can read), prompts (reusable templates), and progress.

Rule of thumb: tools are model-controlled actions, resources are application-controlled context,
prompts are user-controlled templates.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # make `common` importable

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

mcp = MCPServer("demo-resources")

NOTES = {  # in-memory and read-only: no filesystem access to get wrong
    "welcome": "Welcome to the notes server.",
    "roadmap": "Level 4 is MCP. Level 5 is workflows.",
}


@mcp.resource("notes://index")
def notes_index() -> str:
    """List available note names."""
    return "\n".join(sorted(NOTES))


# A URI template: one function serves every note, and `name` is filled from the URI.
@mcp.resource("notes://{name}")
def read_note(name: str) -> str:
    """Read one note by name."""
    if name not in NOTES:
        raise ResourceError(f"No note '{name}'. Read notes://index for the list.")
    return NOTES[name]


@mcp.prompt()
def summarize_note(name: str) -> str:
    """Template asking the model to summarize a note; the user picks it, the host fills it in."""
    return f"Read the resource notes://{name} and summarize it in one sentence."


@mcp.tool()
async def count_slowly(n: int, ctx: Context) -> str:
    """Count to n, reporting progress so a client can show a progress bar."""
    if not 1 <= n <= 20:  # validate inputs even though the schema is typed
        raise ToolError("n must be between 1 and 20.")
    for i in range(1, n + 1):
        await ctx.report_progress(i, n)
    return f"Counted to {n}."


if __name__ == "__main__":
    mcp.run("stdio")
