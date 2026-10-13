"""Offline tests for Level 7: ticket tools, MCP server, approvals, injection red team, crash/resume, eval gate."""
import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import Client

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "03_agents", ROOT / "06_harness", ROOT / "07_enterprise_capstone",
          ROOT / "07_enterprise_capstone" / "ticket_server"):
    sys.path.insert(0, str(p))

import run_evals  # noqa: E402
from approvals import AuditLog, make_approver  # noqa: E402
from ops_agent import build, handle_ticket  # noqa: E402
from server import build_server  # noqa: E402
from ticket_store import TicketStore  # noqa: E402

from common.demo_tools import ToolError  # noqa: E402
from common.scripted import RuleModel, text, tool_use  # noqa: E402


def test_refund_validated_in_code():
    s = TicketStore()
    with pytest.raises(ToolError, match="does not belong"):
        s.issue_refund("T-3", "O-100", 5.0, "x")  # someone else's order
    with pytest.raises(ToolError, match="Amount must be"):
        s.issue_refund("T-1", "O-100", 21.0, "x")  # more than the order
    s.issue_refund("T-1", "O-100", 20.0, "x")
    with pytest.raises(ToolError, match="Amount must be"):
        s.issue_refund("T-1", "O-100", 1.0, "x")  # already fully refunded


def test_mcp_read_only_server_has_no_write_tools():
    async def names(writes):
        async with Client(build_server(TicketStore(), writes=writes)) as c:
            return {t.name for t in (await c.list_tools()).tools}
    assert asyncio.run(names(False)) == {"get_ticket", "search_tickets", "get_order"}
    assert {"issue_refund", "close_ticket"} <= asyncio.run(names(True))


def test_mcp_domain_error_keeps_recovery_message():
    async def go():
        async with Client(build_server(TicketStore(), writes=False)) as c:
            return await c.call_tool("get_ticket", {"ticket_id": "NOPE"})
    r = asyncio.run(go())
    assert r.is_error and "search_tickets" in r.content[0].text


def test_approver_thresholds_and_fail_closed():
    audit = AuditLog(None, "t")
    approve = make_approver(audit, human=None, auto_limit=25)
    assert approve("issue_refund", {"amount": 20}) and not approve("issue_refund", {"amount": 80})
    assert [e["decision"] for e in audit.entries] == ["approved", "denied"]
    assert make_approver(AuditLog(None, "t"), human=lambda n, a: True)("issue_refund", {"amount": 80})


def test_injection_cannot_cause_unauthorised_refund_even_if_model_obeys():
    cases = [c for c in run_evals.load_cases() if "red_team" in c["tags"]]
    assert cases and all(run_evals.run_case(c)["passed"] for c in cases)


def test_ticket_text_is_wrapped_as_untrusted():
    store = TicketStore()
    ops = build(store, "wrap")
    out, _ = ops.execute("get_ticket", {"ticket_id": "T-3"})
    assert "untrusted_tool_output" in out and ops.tracker.tainted


def test_crash_then_resume_refunds_exactly_once(tmp_path):
    class Crash(Exception):
        pass

    script = [[tool_use("a", "get_ticket", ticket_id="T-1")],
              [tool_use("b", "issue_refund", ticket_id="T-1", order_id="O-100", amount=20.0, reason="damaged"),
               tool_use("c", "close_ticket", ticket_id="T-1", resolution="refunded")],
              [text("Done.")]]
    store = TicketStore()  # the "backend": survives the crash, like a real database
    ops = build(store, "crash", workdir=tmp_path)
    inner = ops.execute

    def crashy(name, args):
        if name == "close_ticket":
            raise Crash()  # process dies AFTER the refund, before the round is checkpointed
        return inner(name, args)
    ops.execute = crashy
    with pytest.raises(Crash):
        handle_ticket(RuleModel(script), ops, "T-1", workdir=tmp_path, run_id="crash")
    assert len(store.refunds) == 1

    ops2 = build(store, "crash", workdir=tmp_path)  # a fresh process: new objects, same files
    result = handle_ticket(RuleModel(script), ops2, "T-1", workdir=tmp_path, run_id="crash")
    assert result.stop == "done" and len(store.refunds) == 1  # replayed from the journal, not repeated
    assert store.tickets["T-1"]["status"] == "closed"


def test_eval_gate_opens_on_good_results_and_closes_on_red_team_failure():
    results = [run_evals.run_case(c) for c in run_evals.load_cases()]
    assert run_evals.gate(results)[0]
    bad = [{**r, "passed": False} if "red_team" in r["tags"] else r for r in results]
    ok, why = run_evals.gate(bad)
    assert not ok and "red-team" in why


def test_eval_runner_exit_code(capsys):
    assert run_evals.main() == 0
    assert "RELEASE GATE: OPEN" in capsys.readouterr().out
