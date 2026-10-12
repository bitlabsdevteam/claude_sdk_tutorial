# 4.1 What MCP is

The **Model Context Protocol** is a standard way for an AI application to use tools and data that live in *separate* programs. Think "USB-C for tools": write a capability once as a server, and any MCP-capable app can use it.

## Roles

| Role | What it is | In this repo |
|---|---|---|
| **Host** | The app the user runs; owns the model, the loop, and the permissions | `client_loop.py` and its `run_agent` |
| **Client** | A connector inside the host; one per server connection | `mcp.Client` |
| **Server** | A program that exposes capabilities | `server_basic/`, `server_http/`, `server_resources/` |

## What a server can offer

| Primitive | Controlled by | Use it for |
|---|---|---|
| **Tools** | The model | Actions and lookups (`get_weather`) |
| **Resources** | The application | Read-only context (`notes://roadmap`) |
| **Prompts** | The user | Reusable templates (`summarize_note`) |

## Transports
- **stdio:** the host launches the server as a subprocess. Local, simple, no network auth needed. Never `print()` to stdout in a stdio server.
- **Streamable HTTP:** a remote server at a URL. Needs TLS and authentication (`server_http/`).

## Two ways to use a server with Claude
1. **Your own client** (`client_loop.py`): you connect, list tools, translate them to API tools, and run the loop. Works with stdio and HTTP, tools and resources. You control every call (allowlists, size caps, approvals).
2. **The MCP connector** (`mcp_connector.py`): the API connects to a remote HTTPS server for you. Less code, but tools only, and you control less.

## Local function tool or MCP server?
Use a **local function** when the tool is specific to one app and small. Use an **MCP server** when several apps or teams need it, when it should be owned and deployed separately, when it needs its own credentials, or when you want a standard, swappable interface. MCP adds a process boundary, a protocol, and a new trust boundary (see `mcp_security.md`), so don't use it just for one script.
