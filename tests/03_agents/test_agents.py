"""Mocked tests for Level 3 (no API calls)."""
import importlib.util
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "03_agents"))

from common.budget import Budget, estimate_cost  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(f"l3_{name}", ROOT / "03_agents" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def usage(i=10, o=5, w=0, r=0):
    return NS(input_tokens=i, output_tokens=o, cache_creation_input_tokens=w, cache_read_input_tokens=r)


def msg(stop, *blocks, u=None):
    return NS(stop_reason=stop, content=list(blocks), usage=u or usage())


def tool_use(id_="t1", name="calculate", **inp):
    return NS(type="tool_use", id=id_, name=name, input=inp or {"expression": "1+1"})


def text(t):
    return NS(type="text", text=t)


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls, self.messages = list(responses), [], self

    def create(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def run(responses, **budget_kw):
    agent = load("agent")
    return agent.run_agent(FakeClient(responses), [{"role": "user", "content": "x"}],
                           [], budget=Budget(**budget_kw)), agent


def test_done():
    r, _ = run([msg("end_turn", text("hi"))])
    assert (r.stop, r.text) == ("done", "hi")


def test_refusal_and_truncation():
    assert run([msg("refusal")])[0].stop == "refusal"
    assert run([msg("max_tokens", text("par"))])[0].stop == "truncated"


def test_max_turns_stops_a_looping_model():
    r, _ = run([msg("tool_use", tool_use())], max_turns=3)
    assert r.stop == "max_turns"


def test_token_and_cost_limits():
    assert run([msg("tool_use", tool_use(), u=usage(1000, 1000))], max_total_tokens=1500)[0].stop == "max_tokens"
    assert run([msg("tool_use", tool_use(), u=usage(10, 100_000))], max_cost_usd=0.01,
               max_total_tokens=10**9)[0].stop == "max_cost"


def test_timeout():
    r, _ = run([msg("end_turn")], timeout_s=-1)
    assert r.stop == "timeout"


def test_results_in_one_message_with_errors():
    agent = load("agent")
    client = FakeClient([msg("tool_use", tool_use("a"), tool_use("b", expression="1/0")), msg("end_turn", text("ok"))])
    r = agent.run_agent(client, [{"role": "user", "content": "x"}], [])
    results = r.messages[-2]["content"]
    assert [x["tool_use_id"] for x in results] == ["a", "b"] and [x["is_error"] for x in results] == [False, True]


def test_cost_counts_cache_tokens():
    cheap = estimate_cost(usage(0, 0, 0, 1_000_000), "claude-opus-5-5")
    full = estimate_cost(usage(1_000_000, 0), "claude-opus-5-5")
    assert cheap < full


def test_research_agent_sandbox_and_paging():
    ra = load("research_agent")
    out, err = ra.execute("read_file", {"path": "../../etc/passwd", "offset": 0})
    assert err and "outside" in out
    assert ra.execute("read_file", {"path": ".env", "offset": 0})[1] is True
    out, err = ra.execute("read_file", {"path": "agenda.md", "offset": 0})
    assert not err and "offset=" in out  # large file: pages explicitly, never silently truncated
    assert ra.execute("nope", {})[1] is True


def test_memory_persistence_and_session_name(tmp_path, monkeypatch):
    ma = load("memory_agent")
    monkeypatch.setattr(ma, "STATE_DIR", tmp_path)
    assert ma.execute("remember", {"key": "lang", "value": "python"})[1] is False
    assert "python" in ma.execute("recall", {})[0]
    ma.save_session("s1", [{"role": "user", "content": "hi"},
                           {"role": "assistant", "content": [NS(model_dump=lambda **k: {"type": "text", "text": "yo"})]}])
    assert ma.load_session("s1")[1]["content"][0]["text"] == "yo"
    with pytest.raises(ValueError):
        ma.load_session("../evil")


def test_planner_tools_run_tests(tmp_path):
    pl = load("planner")
    (tmp_path / "calc.py").write_text(pl.BUGGY)
    (tmp_path / "test_calc.py").write_text(pl.TESTS)
    _, execute = pl.make_tools(tmp_path)
    assert execute("run_tests", {})[1] is True  # buggy code fails
    execute("write_calc", {"content": "def average(xs):\n    return sum(xs) / len(xs)\n"})
    assert execute("run_tests", {})[1] is False  # fixed code passes


def test_context_editing_config_shape():
    lc = load("long_context")
    edit = lc.editing_config()["edits"][0]
    assert edit["type"] == "clear_tool_uses_20250919" and edit["keep"]["type"] == "tool_uses"
    assert lc.compaction_config()["edits"][0]["type"] == "compact_20260112"
    assert lc.execute("get_log_chunk", {"n": 1})[1] is False


def test_count_check_fits():
    ct = load("count_tokens")
    models = NS(retrieve=lambda m: NS(max_input_tokens=1000))
    client = NS(models=models, messages=NS(count_tokens=lambda **k: NS(input_tokens=900)))
    assert ct.check_fits(client, [], reserve_output=50) == (900, True)
    assert ct.check_fits(client, [], reserve_output=200) == (900, False)
