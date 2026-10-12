"""4.5 Remote MCP over Streamable HTTP, protected by a bearer token.

Run:  MCP_SERVER_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(32))") python 04_mcp/server_http/server.py
Connect with `mcp.Client("http://127.0.0.1:8000/mcp", ...)` and send `Authorization: Bearer <token>`.
For real deployments use TLS and OAuth (the SDK has an auth provider hook); a static token is the minimum.
"""
import hmac
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # make `common` importable

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from common import demo_tools

mcp = MCPServer("demo-http")


@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate an arithmetic expression using + - * / ** and numbers."""
    try:
        return demo_tools.calculate(expression)
    except demo_tools.ToolError as e:
        raise ToolError(str(e)) from e


class BearerAuth:
    """Pure-ASGI middleware (BaseHTTPMiddleware can break streaming responses)."""

    def __init__(self, app, token: str):
        if not token:  # fail closed: a missing secret must never mean "no auth"
            raise RuntimeError("MCP_SERVER_TOKEN is not set")
        self.app, self.expected = app, f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            given = dict(scope["headers"]).get(b"authorization", b"")
            # compare_digest: constant-time, so response timing doesn't leak the token.
            if not hmac.compare_digest(given, self.expected):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain"), (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
        await self.app(scope, receive, send)


def build_app(token: str):
    return BearerAuth(mcp.streamable_http_app(), token)


if __name__ == "__main__":
    # Secrets come from the environment, never from code or logs. Bind to localhost unless behind a proxy.
    uvicorn.run(build_app(os.environ.get("MCP_SERVER_TOKEN", "")), host="127.0.0.1", port=8000)
