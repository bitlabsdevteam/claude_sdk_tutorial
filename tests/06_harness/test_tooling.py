"""Offline tests for Level 6 tracing + 6B: tracing, harness/policy/hooks, workspace tools, sandbox, PTC."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "03_agents"))

from common.budget import Budget  # noqa: E402
from common.harness import Block, Harness, Policy, Rule  # noqa: E402
from common.tracing import Tracer, load, scrub, summarize, triage  # noqa: E402
from common.workspace_tools import make_workspace  # noqa: E402


def load_mod(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "06_harness" / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


perm = load_mod("permissions.py", "l6_perm")
hooks = load_mod("hooks.py", "l6_hooks")
sandbox = load_mod("sandbox/runner.py", "l6_sandbox")
ptc = load_mod("programmatic_tools.py", "l6_ptc")
from agent import run_agent  # noqa: E402

USAGE = NS(input_tokens=100, output_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=50)


def reply(stop="end_turn", blocks=None, **extra):
    return NS(stop_reason=stop, content=blocks or [NS(type="text", text="ok")], usage=USAGE,
              _request_id="req_x", stop_details=None, **extra)


# ---- tracing -------------------------------------------------------------------

def test_tracer_writes_jsonl_and_scrubs(tmp_path):
    t = Tracer(tmp_path / "t.jsonl", run_id="r1")
    t.event("note", detail="key sk-ant-abcdefghij123 and Bearer abc.def")
    rec = load(tmp_path / "t.jsonl")[0]
    assert rec["run_id"] == "r1" and "sk-ant" not in rec["detail"] and "abc.def" not in rec["detail"]
    assert scrub("plain") == "plain" and scrub(5) == 5


def test_run_agent_emits_one_turn_record_with_tool_timings(tmp_path):
    schemas, handlers = make_workspace(tmp_path)
    (tmp_path / "a.txt").write_text("hello")
    tracer = Tracer()
    harness = Harness(handlers, Policy([Rule("*", "allow")]), tracer=tracer)
    use = NS(type="tool_use", id="1", name="read_file", input={"path": "a.txt"})
    responses = iter([reply("tool_use", [use]), reply("end_turn")])
    client = NS(messages=NS(create=lambda **kw: next(responses)))
    run_agent(client, [{"role": "user", "content": "x"}], schemas, harness.execute, Budget(), tracer=tracer)
    turns = [r for r in tracer.records if r["type"] == "turn"]
    assert [r["turn"] for r in turns] == [1, 2] and turns[0]["request_id"] == "req_x"
    assert turns[0]["cache_read"] == 50 and turns[0]["tools"][0]["name"] == "read_file"
    assert turns[0]["tools"][0]["result_chars"] == 5 and "hello" not in json.dumps(turns)  # sizes, not content


def _turn(i, tokens, tools=(), stop="tool_use", cache=0):
    return {"type": "turn", "turn": i, "stop_reason": stop, "input_tokens": tokens, "output_tokens": 5,
            "cache_read": cache, "cache_write": 0, "latency_s": 0.1, "cost_usd": 0.01, "tools": list(tools)}


def test_summarize_and_triage_layers():
    bad_tool = {"name": "t", "is_error": True, "duration_s": 0.2, "result_chars": 3}
    records = [_turn(1, 100, [bad_tool]), _turn(2, 400, [bad_tool]), _turn(3, 900, [bad_tool])]
    s = summarize(records)
    assert s["tool_errors"] == 3 and s["slowest_tool"] == ("t", 0.2) and s["turns"] == 3
    found = " | ".join(triage(records))
    assert "TOOLS" in found and "CONTEXT: input grew" in found and "HARNESS: run ended" in found
    healthy = [_turn(1, 100, stop="tool_use", cache=0), _turn(2, 100, stop="end_turn", cache=500)]
    assert triage(healthy) == ["no obvious fault: read the turns"]
    denied = [*healthy, {"type": "event", "kind": "denied"}]
    assert any(line.startswith("HARNESS: 1 call(s) denied") for line in triage(denied))
    assert triage([]) == ["no turns recorded"]
    assert any("MODEL/PROMPT" in x for x in triage([_turn(1, 10, stop="refusal")]))


# ---- policy + harness ----------------------------------------------------------

def test_policy_first_match_default_deny_and_args():
    p = perm.default_policy()
    assert p.decide("list_files", {}).verdict == "allow"
    assert p.decide("read_file", {"path": "x.txt"}).verdict == "allow"
    assert p.decide("read_file", {"path": ".env"}).verdict == "deny"  # specific denial listed before the allow
    assert p.decide("write_file", {"path": "a.md", "content": ""}).verdict == "allow"
    assert p.decide("write_file", {"path": "a.sh", "content": ""}).verdict == "ask"
    assert p.decide("send_email", {}).verdict == "deny" and "default" in p.decide("send_email", {}).reason


def test_destructive_tools_are_never_auto_approved():
    p = Policy([Rule("*", "allow")], destructive={"delete_file"})
    assert p.decide("delete_file", {}).verdict == "ask" and p.decide("read_file", {}).verdict == "allow"


def test_wildcard_rules():
    assert Policy([Rule("read_*", "allow")]).decide("read_file", {}).verdict == "allow"
    assert Policy([Rule("read_*", "allow")]).decide("write_file", {}).verdict == "deny"


def make_harness(tmp_path, approve=None, **kw):
    schemas, handlers = make_workspace(tmp_path)
    return Harness(handlers, perm.default_policy(), approve=approve, **kw)


def test_denied_call_never_executes_and_is_a_tool_error(tmp_path):
    (tmp_path / ".env").write_text("SECRET")
    h = make_harness(tmp_path)
    content, is_error = h.execute("read_file", {"path": ".env"})
    assert is_error and "hidden files" in content and "SECRET" not in content
    assert h.tracer.records[-1]["kind"] == "denied"


def test_ask_fails_closed_without_approver_and_waits_for_approval(tmp_path):
    f = tmp_path / "old.txt"
    f.write_text("x")
    assert make_harness(tmp_path).execute("delete_file", {"path": "old.txt"})[1] is True and f.exists()
    assert make_harness(tmp_path, approve=lambda n, a: False).execute("delete_file", {"path": "old.txt"})[1] is True
    assert f.exists()
    asked = []
    h = make_harness(tmp_path, approve=lambda n, a: asked.append((n, a)) or True)
    assert h.execute("delete_file", {"path": "old.txt"}) == ("Deleted old.txt.", False)
    assert asked == [("delete_file", {"path": "old.txt"})] and not f.exists()
    assert "approved" in [r["kind"] for r in h.tracer.records]


def test_pre_hooks_block_and_rewrite_in_order(tmp_path):
    order = []
    h = make_harness(tmp_path, pre_hooks=[lambda n, a: order.append("pre1") or a, hooks.normalize_path,
                                          hooks.block_secrets_in_args])
    assert h.execute("write_file", {"path": "./a.txt", "content": "hi"})[1] is False
    assert (tmp_path / "a.txt").exists() and order == ["pre1"]  # './a.txt' was rewritten to 'a.txt'
    out, err = h.execute("write_file", {"path": "b.txt", "content": "sk-ant-abcdefghij12345"})
    assert err and out.startswith("Blocked") and not (tmp_path / "b.txt").exists()


def test_post_hooks_redact_and_cap_results(tmp_path):
    (tmp_path / "c.txt").write_text("token=Bearer abc123secret " + "x" * 2000)
    h = make_harness(tmp_path, post_hooks=[hooks.redact_secrets, hooks.cap_result])
    out, _ = h.execute("read_file", {"path": "c.txt"})
    assert "abc123secret" not in out and "[REDACTED]" in out
    h2 = Harness({"big": lambda: "y" * 5000}, Policy([Rule("*", "allow")]), post_hooks=[hooks.cap_result])
    assert "[truncated: 4000 more chars]" in h2.execute("big", {})[0]


def test_tool_errors_crashes_and_bad_args_are_contained(tmp_path):
    h = Harness({"boom": lambda: 1 / 0, "needs": lambda x: x}, Policy([Rule("*", "allow")]))
    out, err = h.execute("boom", {})
    assert err and out == "boom failed unexpectedly." and "division" not in out  # no internals to the model
    assert h.tracer.records[-1]["kind"] == "tool_crash"
    assert h.execute("needs", {})[1] is True and "Invalid arguments" in h.execute("needs", {})[0]
    assert "Unknown tool" in h.execute("nope", {})[0]


def test_block_exception_is_exported():
    with pytest.raises(Block):
        hooks.block_secrets_in_args("w", {"content": "sk-ant-abcdefghij12345"})


# ---- workspace tools -----------------------------------------------------------

def test_workspace_confines_paths_and_marks_truncation(tmp_path):
    schemas, h = make_workspace(tmp_path)
    from common.demo_tools import ToolError
    with pytest.raises(ToolError, match="outside the workspace"):
        h["read_file"]("../../etc/passwd")
    with pytest.raises(ToolError):
        h["write_file"]("/tmp/evil.txt", "x")
    (tmp_path / "big.txt").write_text("z" * 5000)
    assert "[truncated: 1000 more chars]" in h["read_file"]("big.txt")
    assert {s["name"] for s in schemas} == set(h) and all(s["strict"] for s in schemas)


# ---- sandbox -------------------------------------------------------------------

def test_sandbox_normal_timeout_env_and_output_cap(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    assert sandbox.run_python("print(6*7)").stdout.strip() == "42"
    env = sandbox.run_python("import os; print(os.environ.get('ANTHROPIC_API_KEY'), len(os.environ))")
    assert env.stdout.startswith("None") and "sk-ant" not in env.stdout
    hung = sandbox.run_python("while True: pass", timeout_s=1, cpu_s=5)
    assert hung.timed_out and hung.returncode is None
    big = sandbox.run_python("print('x' * 100000)", max_output=100)
    assert big.truncated and "output truncated" in big.stdout and len(big.stdout) < 200
    err = sandbox.run_python("raise ValueError('bad')")
    assert err.returncode != 0 and "ValueError" in err.stderr


def test_sandbox_runs_in_throwaway_directory():
    r = sandbox.run_python("import os; open('f.txt','w').write('x'); print(os.getcwd())")
    assert "f.txt" not in r.stdout and not Path(r.stdout.strip()).exists()  # temp dir is gone afterwards


# ---- programmatic tool calling -------------------------------------------------

def test_ptc_tool_definition_rules():
    assert ptc.SALES_TOOL["allowed_callers"] == ["code_execution_20260120"]
    assert "strict" not in ptc.SALES_TOOL  # strict is not supported with programmatic calling
    assert ptc.CODE_EXEC["type"] == "code_execution_20260120"
    assert ptc.execute("get_sales", {"region": "mars"})[1] is True
    rows = json.loads(ptc.get_sales("north"))
    assert len(rows) == 300 and ptc.revenue("north") == sum(r["units"] * r["price"] for r in rows)


def test_ptc_loop_passes_container_and_sends_only_tool_results():
    calls = []
    prog = NS(type="tool_use", id="t1", name="get_sales", input={"region": "north"},
              caller=NS(type="code_execution_20260120"))
    server = NS(type="server_tool_use", id="s1", name="code_execution", input={})
    first = reply("tool_use", [server, prog], container=NS(id="container_1"))
    final = reply("end_turn", [NS(type="text", text="north is highest")])
    responses = iter([first, final])

    def create(**kw):
        calls.append({**kw, "messages": [dict(m) for m in kw["messages"]]})
        return next(responses)

    response, hidden = ptc.run(NS(messages=NS(create=create)), "task", Budget())
    assert response.content[0].text == "north is highest"
    assert "container" not in calls[0] and calls[1]["container"] == "container_1"
    last_user = calls[1]["messages"][-1]
    assert last_user["role"] == "user" and all(b["type"] == "tool_result" for b in last_user["content"])
    assert hidden == len(ptc.get_sales("north"))  # programmatic output counted as kept out of context
    assert calls[0]["tools"][0]["type"] == "code_execution_20260120" and "tool_choice" not in calls[0]


def test_ptc_loop_is_bounded():
    prog = NS(type="tool_use", id="t", name="get_sales", input={"region": "north"}, caller=NS(type="direct"))
    client = NS(messages=NS(create=lambda **kw: reply("tool_use", [prog])))
    with pytest.raises(RuntimeError):
        ptc.run(client, "task", Budget(max_turns=50), max_turns=3)
