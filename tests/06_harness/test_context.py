"""Offline tests for Level 6A: context budget, compaction, append-only, cache architecture, JIT context."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from common.budget import Budget  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(f"l6_{name}", ROOT / "06_harness" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"l6_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


cb, comp, ao, ca, jit = (load(n) for n in ["context_budget", "compaction", "append_only",
                                           "cache_architecture", "jit_context"])
USAGE = NS(input_tokens=10, output_tokens=5, cache_creation_input_tokens=0, cache_read_input_tokens=0)


class FakeClient:
    def __init__(self, text):
        self.text, self.prompts, self.messages = text, [], self

    def create(self, **kw):
        self.prompts.append(kw["messages"][0]["content"])
        return NS(stop_reason="end_turn", usage=USAGE, content=[NS(type="text", text=self.text)])


# ---- 6.1 -----------------------------------------------------------------------

def test_context_plan_thresholds_and_advice():
    ok = cb.ContextPlan(working_budget=10_000, reserve_output=2_000, parts={"system": 100, "retrieved": 500})
    assert ok.fits and not ok.should_compact and ok.advice() == []
    near = cb.ContextPlan(10_000, 2_000, {"system": 100, "history": 6_500})  # 6,600 >= 80% of 8,000 usable
    assert near.fits and near.should_compact
    over = cb.ContextPlan(10_000, 2_000, {"system": 100, "tools": 500, "retrieved": 9_000})
    assert not over.fits
    assert over.advice()[0].startswith("retrieved") and "just-in-time" in over.advice()[0]  # biggest first
    assert "OVER BUDGET" in over.report()


def test_measure_has_all_components():
    parts = cb.measure("sys", [{"name": "t"}], [{"role": "user", "content": "x"}], "doc")
    assert set(parts) == {"system", "tools", "history", "retrieved"} and all(v > 0 for v in parts.values())


# ---- 6.2 -----------------------------------------------------------------------

def test_safe_to_compact_rules():
    tool_use = NS(type="tool_use", id="1", name="x", input={})
    text = {"type": "text", "text": "hi"}
    assert not comp.safe_to_compact([])
    assert comp.safe_to_compact([{"role": "user", "content": "q"}, {"role": "assistant", "content": [text]}])
    assert not comp.safe_to_compact([{"role": "user", "content": "q"}, {"role": "assistant", "content": [tool_use]}])
    results = [{"type": "tool_result", "tool_use_id": "1", "content": "ok"}]
    assert not comp.safe_to_compact([{"role": "assistant", "content": [tool_use]}, {"role": "user", "content": results}])
    assert comp.safe_to_compact([{"role": "user", "content": "plain text turn"}])


def test_compact_returns_single_summary_message():
    history = [{"role": "user", "content": "Use psycopg3. Start with invoices."},
               {"role": "assistant", "content": "ok"}]
    fake = FakeClient("GOAL: migrate; DECISION: psycopg3")
    out = comp.compact(fake, history, Budget())
    assert len(out) == 1 and out[0]["role"] == "user" and "psycopg3" in out[0]["content"]
    assert "Use psycopg3. Start with invoices." in fake.prompts[0]  # full transcript sent, nothing cut
    assert "KEEP:" in fake.prompts[0] and "DROP:" in fake.prompts[0]


def test_compact_refuses_mid_tool_round():
    pending = [{"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": "x", "input": {}}]}]
    with pytest.raises(ValueError):
        comp.compact(FakeClient("s"), pending, Budget())


def test_needs_compaction():
    big = [{"role": "user", "content": "x" * 4_000}]
    assert comp.needs_compaction(big, 500) and not comp.needs_compaction(big, 5_000)


# ---- 6.3 -----------------------------------------------------------------------

T = [{"name": "run", "description": "d", "input_schema": {}}]
BASE = {"system": "S", "tools": T, "messages": [{"role": "user", "content": "hi"}]}
REPLY = {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                                          {"type": "text", "text": "yo"}]}


def grow(req, *msgs):
    return {**req, "messages": [*req["messages"], *msgs]}


def test_append_only_is_clean():
    assert ao.violations(BASE, grow(BASE, REPLY, {"role": "user", "content": "more"})) == []


def test_system_tool_and_message_edits_detected():
    nxt = grow(BASE, REPLY, {"role": "user", "content": "more"})
    assert "system prompt changed" in ao.violations(BASE, {**nxt, "system": "S2"})[0]
    assert "removed" in ao.violations(BASE, {**nxt, "tools": []})[0]
    assert "definition changed" in ao.violations(BASE, {**nxt, "tools": [{**T[0], "description": "new"}]})[0]
    assert "shortened" in ao.violations(nxt, BASE)[0]
    edited = {**nxt, "messages": [{"role": "user", "content": "HI"}, *nxt["messages"][1:]]}
    assert "message 0 was edited" in ao.violations(nxt, edited)[0]


def test_allowed_changes_are_not_flagged():
    nxt = grow(BASE, REPLY, {"role": "user", "content": "more"})
    cached = {**nxt, "messages": [{"role": "user", "content": [{"type": "text", "text": "hi",
                                                                 "cache_control": {"type": "ephemeral"}}]},
                                  *nxt["messages"][1:]]}
    assert ao.violations({**BASE, "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]},
                         cached) == []  # cache_control markers don't count as edits
    two = {**BASE, "tools": [*T, {"name": "b", "description": "d", "input_schema": {}}]}
    assert ao.violations(two, {**nxt, "tools": list(reversed(two["tools"]))}) == []  # reorder ok
    deferred = {**nxt, "tools": [*T, {"name": "late", "defer_loading": True, "input_schema": {}}]}
    assert ao.violations(BASE, deferred) == []
    eager = {**nxt, "tools": [*T, {"name": "late", "input_schema": {}}]}
    assert "declare it up front" in ao.violations(BASE, eager)[0]


def test_sdk_objects_compare_like_dicts():
    block = NS(model_dump=lambda **k: {"type": "text", "text": "yo"})
    a = {**BASE, "messages": [*BASE["messages"], {"role": "assistant", "content": [block]}]}
    b = {**BASE, "messages": [*BASE["messages"], {"role": "assistant", "content": [{"type": "text", "text": "yo"}]}]}
    assert ao.violations(a, grow(b, {"role": "user", "content": "x"})) == []


def test_check_session_reports_turn_index():
    t2 = grow(BASE, REPLY, {"role": "user", "content": "m"})
    t3 = {**grow(t2, REPLY, {"role": "user", "content": "n"}), "system": "CHANGED"}
    assert [i for i, _ in ao.check_session([BASE, t2, t3])] == [2]


def test_binding_check_kwargs():
    kw = ao.binding_check_kwargs("drop_block")
    assert kw["betas"] == ["thinking-binding-controls-2026-08-01"]
    assert kw["thinking"] == {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
    with pytest.raises(AssertionError):
        ao.binding_check_kwargs("ignore")


# ---- 6.4 -----------------------------------------------------------------------

def test_audit_system_finds_cache_busters():
    assert ca.audit_system("Be nice. Policy v2.") == []
    hits = ca.audit_system("Now: 2026-10-12T09:15. Session id: 7")
    assert len(hits) == 2 and any("timestamp" in h for h in hits)
    assert ca.audit_system("id 123e4567-e89b-12d3-a456-426614174000")


def test_volatile_note_appended_last_and_prefix_preserved():
    h1 = [{"role": "user", "content": "q1"}]
    r1 = ca.build_request("S", [], h1, "time 1")
    assert r1["messages"][-1] == {"role": "system", "content": "time 1"}
    h2 = [*r1["messages"], {"role": "assistant", "content": "a"}, {"role": "user", "content": "q2"}]
    assert ao.violations(r1, ca.build_request("S", [], h2, "time 2")) == []
    with pytest.raises(ValueError):
        ca.with_volatile([{"role": "assistant", "content": "a"}], "x")


# ---- 6.5 -----------------------------------------------------------------------

def test_catalog_is_small_and_topics_load_on_demand():
    names = list(jit.catalog())
    assert "02_tools" in names and "05_workflows" in names
    assert len(jit.list_topics()) * 5 < len(jit.upfront_text())  # catalog is far smaller than everything
    assert "Level 2" in jit.load_topic("02_tools")


def test_load_topic_is_confined_and_errors_are_tool_errors():
    with pytest.raises(KeyError):
        jit.load_topic("../../etc/passwd")
    text, is_error = jit.execute("load_topic", {"name": "nope"})
    assert is_error and "list_topics" in text
    assert jit.execute("list_topics", {})[1] is False and jit.execute("rm", {})[1] is True


def test_truncation_is_explicit(monkeypatch):
    monkeypatch.setattr(jit, "MAX_TOPIC_CHARS", 50)
    assert "[truncated:" in jit.load_topic("02_tools")
