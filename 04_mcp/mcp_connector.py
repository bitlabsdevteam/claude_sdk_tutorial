"""4.4 The MCP connector: the API itself connects to a REMOTE MCP server, so you write no client or loop.

Needs a publicly reachable HTTPS MCP server (e.g. 4.5 behind a tunnel). Set MCP_SERVER_URL and MCP_SERVER_TOKEN.
Trade-off vs 4.3: less code, but only remote HTTP servers and only tools (no resources, prompts, or stdio).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, make_client

BETA = "mcp-client-2025-11-20"


def build_request(url: str, token: str | None, allowed: list[str], name: str = "demo") -> dict:
    """Both halves are required: the server definition AND a toolset that references it by name."""
    server = {"type": "url", "url": url, "name": name}
    if token:
        server["authorization_token"] = token  # sent to the MCP server as a bearer token
    return {
        "mcp_servers": [server],
        "tools": [{
            "type": "mcp_toolset",
            "mcp_server_name": name,
            # Allowlist: disable everything, then enable only the tools we chose.
            "default_config": {"enabled": False},
            "configs": {t: {"enabled": True} for t in allowed},
        }],
    }


def main() -> None:
    url = os.environ.get("MCP_SERVER_URL")
    if not url:
        sys.exit("Set MCP_SERVER_URL (public https URL of an MCP server) and optionally MCP_SERVER_TOKEN.")
    response = make_client().beta.messages.create(
        model=MODEL, max_tokens=2048, betas=[BETA], output_config={"effort": "low"},
        messages=[{"role": "user", "content": "Use the calculate tool: what is 12 * 12?"}],
        **build_request(url, os.environ.get("MCP_SERVER_TOKEN"), allowed=["calculate"]),
    )
    # Unlike client tools, the API already ran the tool: results arrive in the SAME response.
    if response.stop_reason == "refusal":
        print("Refused:", response.stop_details)
        return
    for block in response.content:
        if block.type == "mcp_tool_use":
            print(f"[mcp call] {block.server_name}.{block.name} {block.input}")
        elif block.type == "mcp_tool_result":
            print(f"[mcp result] error={block.is_error}")
        elif block.type == "text":
            print(block.text)


if __name__ == "__main__":
    main()
