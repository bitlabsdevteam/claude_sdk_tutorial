"""Mocked tests for Level 2 (no API calls)."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "02_tools"))  # sibling imports inside the level

from common.demo_tools import calculate, get_weather, run_tool, ToolError  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "02_tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def msg(stop, *blocks):
    return NS(stop_reason=stop, content=list(blocks), stop_details=None,
              usage=NS(input_tokens=1, output_tokens=1))


def tool_use(id_, name, **inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def text(t):
    return NS(type="text", text=t)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append([dict(m) for m in kw["messages"]])
        return self.responses.pop(0)


def test_calculate_safe():
    assert calculate("(3 + 4) * 2") == "14"
    with pytest.raises(ToolError):
        calculate("__import__('os').system('x')")
    assert run_tool("calculate", {"expression": "1/0"}) == ("Division by zero.", True)


def test_weather_error_is_helpful():
    content, is_error = run_tool("get_weather", {"location": "Atlantis", "unit": "celsius"})
    assert is_error and "paris" in content
    assert get_weather("Paris", "fahrenheit").startswith("64")


def test_unknown_tool_and_bad_args():
    assert run_tool("nope", {})[1] is True
    assert run_tool("get_weather", {"bogus": 1})[1] is True


def test_loop_returns_all_results_in_one_message():
    loop = load("manual_loop")
    client = FakeClient([
        msg("tool_use", tool_use("a", "get_weather", location="Paris", unit="celsius"),
            tool_use("b", "calculate", expression="2+2")),
        msg("end_turn", text("done")),
    ])
    messages = [{"role": "user", "content": "hi"}]
    resp = loop.run_loop(client, messages, loop.TOOLS)
    assert loop.final_text(resp) == "done"
    results = messages[-1]["content"]
    assert messages[-1]["role"] == "user" and [r["tool_use_id"] for r in results] == ["a", "b"]
    assert all(not r["is_error"] for r in results)


def test_parallel_executor_marks_errors():
    par = load("parallel_tools")
    out = par.execute_in_parallel([
        tool_use("a", "get_weather", location="Tokyo", unit="celsius"),
        tool_use("b", "get_weather", location="Atlantis", unit="celsius"),
    ])
    assert [r["tool_use_id"] for r in out] == ["a", "b"]
    assert [r["is_error"] for r in out] == [False, True]


def test_loop_is_bounded():
    loop = load("manual_loop")
    forever = [msg("tool_use", tool_use(str(i), "calculate", expression="1+1")) for i in range(3)]
    with pytest.raises(RuntimeError):
        loop.run_loop(FakeClient(forever), [{"role": "user", "content": "x"}], loop.TOOLS, max_turns=3)


def test_server_tools_resumes_pause_turn():
    st = load("server_tools")
    client = FakeClient([msg("pause_turn", text("partial")), msg("end_turn", text("full"))])
    resp = st.run(client, "q", st.DEMOS["search"]["tools"])
    assert resp.stop_reason == "end_turn" and len(client.calls[1]) == 2
