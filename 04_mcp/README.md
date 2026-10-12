# Level 4: MCP (Model Context Protocol)

Run from the project root with the venv active. Until now every tool was a Python function inside the agent. MCP puts tools in separate servers that any app can connect to. Use it when a capability is shared, separately owned, or needs its own credentials; for one small script a local function is simpler.

Uses `mcp` 2.x (`MCPServer`, which was called `FastMCP` in 1.x). `pip install mcp` (it is in `requirements.txt`).

| Item | Concept | Run |
|---|---|---|
| `mcp_overview.md` | Hosts, clients, servers; tools vs resources vs prompts | read it |
| `server_basic/server.py` | A stdio MCP server with 2 read-only tools | launched by the client |
| `client_loop.py` | **MCP client inside your bounded agent loop** (allowlist, size cap) | `python 04_mcp/client_loop.py` |
| `mcp_connector.py` | The API connects to a remote server for you (beta) | `MCP_SERVER_URL=https://... python 04_mcp/mcp_connector.py` |
| `server_http/server.py` | Streamable HTTP with fail-closed bearer auth | `MCP_SERVER_TOKEN=... python 04_mcp/server_http/server.py` |
| `server_resources/server.py` | Resources, prompts, progress, errors | `python 04_mcp/server_resources/server.py` |
| `tool_search.py` | `defer_loading` + tool search for many tools | `python 04_mcp/tool_search.py` |
| `mcp_security.md` | Untrusted output, injection, allowlists, least privilege | read it |

Tests (`pytest tests/04_mcp`) run the real servers in-process with no API calls or network. `client_loop.py` and `tool_search.py` make paid calls, each capped by a `Budget`. `mcp_connector.py` needs a publicly reachable HTTPS server.

## Things to try

- Inspect a server: `npx @modelcontextprotocol/inspector .venv/bin/python 04_mcp/server_basic/server.py`.
- In `client_loop.py`, remove `calculate` from the allowlist and see what the model can no longer do.
- Add a tool to `server_basic/server.py`: it is invisible to the agent until you allowlist it. Why is that good?
- Run `tool_search.py` with `build_tools(defer=False)` and compare first-turn `in=` tokens.

## Checkpoint

When should a capability be an MCP server instead of a local function tool?

When more than one app or team needs it, when it should be deployed and owned separately, when it holds its own credentials or privileges, or when you want a standard swappable interface. Otherwise the extra process, protocol, and trust boundary aren't worth it.

## Next

Level 5: `05_workflows/`.
