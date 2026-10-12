"""Mocked/in-process tests for Level 4 (no API calls, no network, no subprocesses)."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from mcp import Client

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "04_mcp" / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


basic = load("server_basic/server.py", "l4_basic")
loop = load("client_loop.py", "l4_loop")
res = load("server_resources/server.py", "l4_res")
http = load("server_http/server.py", "l4_http")
conn = load("mcp_connector.py", "l4_conn")
search = load("tool_search.py", "l4_search")

ALLOWED = {"get_weather", "calculate"}


def with_bridge(fn, max_chars=None):
    async def run():
        async with Client(basic.mcp) as c:  # in-process: the real server, no subprocess
            kw = {"max_chars": max_chars} if max_chars else {}
            return await fn(loop.McpToolBridge(c, ALLOWED, **kw))
    return asyncio.run(run())


def test_api_tools_translated_and_allowlisted():
    tools = with_bridge(lambda b: b.api_tools())
    assert {t["name"] for t in tools} == ALLOWED
    assert all("input_schema" in t and t["description"] for t in tools)

    async def narrow(_):
        async with Client(basic.mcp) as c:
            return await loop.McpToolBridge(c, {"calculate"}).api_tools()
    assert [t["name"] for t in asyncio.run(narrow(None))] == ["calculate"]


def test_call_success_and_helpful_error():
    assert with_bridge(lambda b: b.call("calculate", {"expression": "3*4"})) == ("12", False)
    text, is_error = with_bridge(lambda b: b.call("get_weather", {"location": "Atlantis", "unit": "celsius"}))
    assert is_error and "Known cities" in text  # the recovery hint survives the protocol


def test_disallowed_tool_blocked_at_call_time():
    text, is_error = with_bridge(lambda b: b.call("delete_everything", {}))
    assert is_error and "not allowed" in text


def test_result_truncation_is_explicit():
    text, _ = with_bridge(lambda b: b.call("get_weather", {"location": "paris", "unit": "celsius"}), max_chars=5)
    assert "[truncated:" in text


def test_agent_loop_over_mcp_with_fake_model():
    def msg(stop, *blocks):
        return NS(stop_reason=stop, content=list(blocks),
                  usage=NS(input_tokens=1, output_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0))

    use = NS(type="tool_use", id="t1", name="calculate", input={"expression": "6*7"})
    done = NS(type="text", text="42")
    seen = []

    class Fake:
        messages = None
        def __init__(self):
            self.messages = self
            self.queue = [msg("tool_use", use), msg("end_turn", done)]
        def create(self, **kw):
            seen.append([dict(m) for m in kw["messages"]])
            return self.queue.pop(0)

    async def run():
        async with Client(basic.mcp) as c:
            bridge = loop.McpToolBridge(c, ALLOWED)
            return await loop.run_with_mcp(Fake(), bridge, "q", loop.Budget(max_turns=4))

    result = asyncio.run(run())
    assert result.stop == "done"
    tool_result = seen[1][-1]["content"][0]  # what the model was sent back
    assert tool_result["tool_use_id"] == "t1" and tool_result["content"] == "42" and tool_result["is_error"] is False


def test_resources_prompts_and_progress():
    async def run():
        async with Client(res.mcp) as c:
            index = await c.read_resource("notes://index")
            note = await c.read_resource("notes://roadmap")
            prompt = await c.get_prompt("summarize_note", {"name": "welcome"})
            progress = []

            async def on_progress(p, total, msg):
                progress.append((p, total))
            counted = await c.call_tool("count_slowly", {"n": 3}, progress_callback=on_progress)
            bad = await c.call_tool("count_slowly", {"n": 99})
            return index, note, prompt, progress, counted, bad

    index, note, prompt, progress, counted, bad = asyncio.run(run())
    assert "welcome" in index.contents[0].text and "Level 4" in note.contents[0].text
    assert "notes://welcome" in prompt.messages[0].content.text
    assert [p for p, _ in progress] == [1, 2, 3]
    assert not counted.is_error and bad.is_error


def test_missing_resource_is_an_error():
    async def run():
        async with Client(res.mcp) as c:
            await c.read_resource("notes://nope")
    with pytest.raises(Exception):
        asyncio.run(run())


def _call_asgi(app, headers):
    sent = []

    async def send(m):
        sent.append(m)

    async def receive():
        return {"type": "http.request"}

    asyncio.run(app({"type": "http", "headers": headers}, receive, send))
    return sent


def test_bearer_auth_fails_closed_and_checks_token():
    with pytest.raises(RuntimeError):
        http.BearerAuth(lambda *a: None, "")  # missing secret must not mean "no auth"

    called = []

    async def inner(scope, receive, send):
        called.append(1)

    app = http.BearerAuth(inner, "s3cret")
    assert _call_asgi(app, [])[0]["status"] == 401
    assert _call_asgi(app, [(b"authorization", b"Bearer wrong")])[0]["status"] == 401
    assert not called
    _call_asgi(app, [(b"authorization", b"Bearer s3cret")])
    assert called == [1]


def test_connector_request_has_both_halves_and_allowlist():
    req = conn.build_request("https://x.example/mcp", "tok", ["calculate"])
    server, toolset = req["mcp_servers"][0], req["tools"][0]
    assert server["authorization_token"] == "tok" and toolset["mcp_server_name"] == server["name"]
    assert toolset["default_config"] == {"enabled": False}
    assert toolset["configs"] == {"calculate": {"enabled": True}}
    assert "authorization_token" not in conn.build_request("https://x/mcp", None, [])["mcp_servers"][0]


def test_tool_search_setup():
    tools = search.build_tools()
    searcher = [t for t in tools if t.get("name") == "tool_search_tool_bm25"][0]
    assert "defer_loading" not in searcher  # the search tool must stay loaded
    others = [t for t in tools if t is not searcher]
    assert len(others) == 30 and all(t["defer_loading"] for t in others)
    assert not any("defer_loading" in t for t in search.build_tools(defer=False))
