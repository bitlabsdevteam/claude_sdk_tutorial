"""Offline tests for the optional Jev triage: adapter validation, routing thresholds, safety, token narrowing.
Jev is a fake transport here; no network, no API key."""
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "03_agents", ROOT / "06_harness", ROOT / "07_enterprise_capstone"):
    sys.path.insert(0, str(p))

import pytest  # noqa: E402
import triage  # noqa: E402
from ops_agent import TOOL_SCHEMAS, build, handle_ticket  # noqa: E402
from ticket_store import TicketStore  # noqa: E402

from common import jev  # noqa: E402
from common.scripted import RuleModel, text, tool_use  # noqa: E402


def fake(lane="refund", lane_p=0.9, risk="low", inj=0.02, model="jev-1.13.0"):
    def transport(payload, timeout):
        rest = (1 - lane_p) / 3
        probs = {k: rest for k in [*triage.QUESTIONS["lane"].options, jev.UNKNOWN]}
        probs[lane] = lane_p
        return {"model": model, "answers": {
            "lane": {"probabilities": probs},
            "risk": {"probabilities": {r: 0.9 if r == risk else 0.05 for r in ("low", "medium", "high")}},
            "injection_suspected": {"probability": inj}}}
    return transport


def route(**kw):
    return triage.decide_route({"x": 1}, transport=fake(**kw))


# ---- adapter ----
def test_every_choice_gets_an_other_option():
    payload = jev._payload({}, triage.QUESTIONS, "jev-1.13")
    assert jev.UNKNOWN in payload["questions"]["lane"]["options"]


@pytest.mark.parametrize("raw", [{}, {"answers": {}}, {"model": "jev-2.0", "answers": {}}])
def test_bad_or_wrong_version_response_returns_none(raw):
    assert jev._parse(raw, triage.QUESTIONS, "jev-1.13") is None


def test_probability_out_of_range_or_unknown_option_rejected():
    bad = fake()({}, 1)
    bad["answers"]["injection_suspected"]["probability"] = 1.5
    assert jev._parse(bad, triage.QUESTIONS, "jev-1.13") is None
    bad = fake()({}, 1)
    bad["answers"]["lane"]["probabilities"]["invented"] = 0.1
    assert jev._parse(bad, triage.QUESTIONS, "jev-1.13") is None


def test_retries_only_retryable_errors(monkeypatch):
    monkeypatch.setattr(jev.time, "sleep", lambda s: None)
    calls = []

    def flaky(code):
        def t(payload, timeout):
            calls.append(code)
            raise urllib.error.HTTPError("u", code, "x", {}, None)
        return t
    assert jev.decide({}, triage.QUESTIONS, transport=flaky(503)) is None and len(calls) == 3  # retried
    calls.clear()
    assert jev.decide({}, triage.QUESTIONS, transport=flaky(401)) is None and len(calls) == 1  # not retried


def test_missing_key_does_not_crash(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert jev.decide({}, triage.QUESTIONS) is None


# ---- state privacy ----
def test_state_has_no_customer_text():
    t = TicketStore().tickets["T-3"]
    state = triage.build_state(t)
    assert t["subject"] not in str(state) and t["body"] not in str(state)
    assert state["instruction_like_phrases"] >= 1


# ---- routing ----
def test_routes():
    assert route(lane="refund").action == "agent" and "issue_refund" in route(lane="refund").tools
    assert "issue_refund" not in route(lane="order_status", risk="medium").tools
    assert route(lane="order_status").action == "template"
    assert route(inj=0.97).action == "human" and route(risk="high").action == "human"
    assert route(lane_p=0.5).tools == triage.FULL  # not confident: full agent, never a guess
    assert route(lane="other").tools == triage.FULL


def test_jev_failure_falls_back_to_haiku_then_to_full_agent():
    def down(payload, timeout):
        raise ConnectionError

    parsed = triage._Haiku(lane="order_status", lane_confidence=0.9, risk="low", injection_probability=0.0)
    usage = SimpleNamespace(input_tokens=50, output_tokens=10, cache_creation_input_tokens=0,
                            cache_read_input_tokens=0)
    client = SimpleNamespace(messages=SimpleNamespace(parse=lambda **kw: SimpleNamespace(
        stop_reason="end_turn", usage=usage, parsed_output=parsed, content=[])))
    r = triage.decide_route({"x": 1}, transport=down, client=client)
    assert (r.source, r.action) == ("haiku", "template")
    r = triage.decide_route({"x": 1}, transport=down, client=None)
    assert (r.source, r.action, r.tools) == ("default", "agent", triage.FULL)


# ---- integration with the agent ----
def run(ticket_id, rt, script=None):
    store = TicketStore()
    ops = build(store, "tri")
    model = RuleModel(script or [[text("ok")]])
    result = handle_ticket(model, ops, ticket_id, triage=lambda s: rt, run_id="tri")
    return store, result, model


def test_human_route_escalates_without_a_model_call():
    store, result, model = run("T-3", route(inj=0.97))
    assert result.stop == "triaged_human" and model.calls == 0
    assert store.tickets["T-3"]["status"] == "escalated" and store.refunds == []


def test_template_route_replies_without_a_model_call():
    store, result, model = run("T-2", route(lane="order_status"))
    assert result.stop == "triaged_template" and model.calls == 0 and len(store.replies) == 1


def test_narrowed_tools_are_enforced_not_just_advertised():
    sent = []
    model = RuleModel([[tool_use("1", "issue_refund", ticket_id="T-2", order_id="O-200", amount=5.0, reason="x")],
                       [text("done")]])
    orig = model.create
    model.create = lambda **kw: (sent.append({t["name"] for t in kw["tools"]}), orig(**kw))[1]  # record the tool set
    store, result, _ = None, None, None
    store = TicketStore()
    ops = build(store, "tri2")
    handle_ticket(model, ops, "T-2", triage=lambda s: route(lane="order_status", risk="medium"), run_id="tri2")
    assert "issue_refund" not in sent[0] and len(sent[0]) < len(TOOL_SCHEMAS)  # fewer schemas sent
    assert store.refunds == []  # and the call the model made anyway was refused


def test_without_triage_behaviour_is_unchanged():
    store = TicketStore()
    ops = build(store, "none")
    result = handle_ticket(RuleModel([[text("ok")]]), ops, "T-1", run_id="none")
    assert result.stop == "done"
