"""Mocked tests for Level 5 (no API calls)."""
import importlib.util
import sys
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from common.budget import Budget  # noqa: E402
from common.llm import LLMError, ask  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(f"l5_{name}", ROOT / "05_workflows" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"l5_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


USAGE = NS(input_tokens=10, output_tokens=5, cache_creation_input_tokens=0, cache_read_input_tokens=0)


def reply(text="ok", parsed=None, stop="end_turn", blocks=None):
    return NS(stop_reason=stop, content=blocks if blocks is not None else [NS(type="text", text=text)],
              usage=USAGE, parsed_output=parsed, stop_details=None)


class Fake:
    """handler(kind, kwargs) -> response; kind is 'create' or 'parse'. Records every call."""

    def __init__(self, handler):
        self.handler, self.calls, self.messages = handler, [], self

    def create(self, **kw):
        self.calls.append(("create", kw))
        return self.handler("create", kw)

    def parse(self, **kw):
        self.calls.append(("parse", kw))
        return self.handler("parse", kw)


def prompt_of(kw):
    return kw["messages"][0]["content"]


# ---- common/llm.py and Budget -------------------------------------------------

def test_ask_checks_stop_reason_and_budget():
    with pytest.raises(LLMError):
        ask(Fake(lambda k, kw: reply(stop="refusal")), "x")
    with pytest.raises(LLMError):
        ask(Fake(lambda k, kw: reply(stop="max_tokens")), "x")
    spent = Budget(max_turns=0)
    fake = Fake(lambda k, kw: reply())
    with pytest.raises(LLMError):
        ask(fake, "x", budget=spent)
    assert fake.calls == []  # refused BEFORE spending


def test_ask_parse_path_and_effort_kept():
    fake = Fake(lambda k, kw: reply(parsed="OBJ"))
    assert ask(fake, "x", schema=dict) == "OBJ"
    kind, kw = fake.calls[0]
    assert kind == "parse" and kw["output_format"] is dict and kw["output_config"] == {"effort": "low"}


def test_budget_is_thread_safe_and_absorbs():
    b = Budget()
    threads = [threading.Thread(target=lambda: [b.record(USAGE, "claude-opus-5-5") for _ in range(200)])
               for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert b.turns == 1600 and b.tokens == 1600 * 15
    other = Budget()
    other.record(USAGE, "claude-opus-5-5")
    b.absorb(other)
    assert b.turns == 1601


# ---- 5.1 chain -----------------------------------------------------------------

def test_chain_stops_at_failed_gate():
    chain = load("chain")
    fake = Fake(lambda k, kw: reply("- only one bullet"))
    result = chain.run_chain(fake, "t", Budget())
    assert not result.ok and "gate failed" in result.reason
    assert len(fake.calls) == 1  # step 2 never ran


def test_chain_happy_path():
    chain = load("chain")
    fake = Fake(lambda k, kw: reply("- a\n- b\n- c"))
    result = chain.run_chain(fake, "t", Budget())
    assert result.ok and len(fake.calls) == 2
    assert "- a" in prompt_of(fake.calls[1][1])  # step 1's output fed step 2


# ---- 5.2 router ----------------------------------------------------------------

def test_router_dispatches_to_matching_prompt():
    router = load("router")

    def handler(kind, kw):
        return reply(parsed=router.Route(category="billing")) if kind == "parse" else reply("refunded")

    fake = Fake(handler)
    category, answer = router.handle(fake, "charged twice", Budget())
    assert (category, answer) == ("billing", "refunded")
    assert fake.calls[1][1]["system"] == router.HANDLERS["billing"]
    with pytest.raises(Exception):
        router.Route(category="astrology")  # the classifier cannot invent a label


# ---- 5.3 parallel --------------------------------------------------------------

def test_sectioning_tolerates_one_failed_branch():
    par = load("parallel")

    def handler(kind, kw):
        if "performance" in prompt_of(kw):
            return reply(stop="refusal")
        return reply("fine")

    out = par.sectioning(Fake(handler), "code", Budget())
    assert out == {"security": "fine", "performance": None, "readability": "fine"}


def test_voting_takes_majority():
    par = load("parallel")
    votes = iter(["yes", "no", "yes"])
    fake = Fake(lambda k, kw: reply(parsed=par.Verdict(safe=next(votes))))
    winner, tally = par.voting(fake, "msg", Budget(), n=3)
    assert winner == "yes" and tally["yes"] == 2


# ---- 5.4 orchestrator ----------------------------------------------------------

def test_orchestrator_caps_subtasks_and_says_so(capsys):
    orch = load("orchestrator")
    plan = orch.Plan(subtasks=[f"t{i}" for i in range(7)])
    fake = Fake(lambda k, kw: reply(parsed=plan) if k == "parse" else reply("done"))
    orch.run(fake, "goal", Budget())
    assert len(fake.calls) == 1 + orch.MAX_SUBTASKS + 1  # plan + capped workers + synthesis
    assert "running the first 4" in capsys.readouterr().out


def test_orchestrator_rejects_empty_plan():
    orch = load("orchestrator")
    with pytest.raises(LLMError):
        orch.run(Fake(lambda k, kw: reply(parsed=orch.Plan(subtasks=[]))), "goal", Budget())


# ---- 5.5 evaluator-optimizer ---------------------------------------------------

def test_eval_opt_converges():
    eo = load("eval_opt")
    verdicts = iter([False, True])
    fake = Fake(lambda k, kw: reply(parsed=eo.Critique(passed=next(verdicts), feedback="shorter"))
                if k == "parse" else reply("draft"))
    out = eo.run(fake, "task", Budget())
    assert out.converged and out.rounds == 2


def test_eval_opt_is_bounded():
    eo = load("eval_opt")
    fake = Fake(lambda k, kw: reply(parsed=eo.Critique(passed=False, feedback="no"))
                if k == "parse" else reply("draft"))
    out = eo.run(fake, "task", Budget(), max_rounds=3)
    assert not out.converged and out.rounds == 3
    assert len(fake.calls) == 1 + 3 + 2  # draft + 3 critiques + 2 refinements (none after the last critique)


# ---- 5.6 subagents -------------------------------------------------------------

def test_handoff_contract_is_enforced():
    sub = load("subagents")
    with pytest.raises(Exception):
        sub.Handoff(summary="x" * 501)


def test_parent_sees_only_the_handoff():
    sub = load("subagents")
    raw = "RAW-TOOL-DUMP " * 50

    def handler(kind, kw):
        if kind == "parse":
            return reply(parsed=sub.Handoff(summary="short summary", sources=["a.md"]))
        if "tools" in kw:  # the subagent's own loop
            return reply(raw)
        return reply("combined")  # parent synthesis

    fake = Fake(handler)
    assert sub.run(fake, ["q1", "q2"], Budget()) == "combined"
    parent_prompt = prompt_of(fake.calls[-1][1])
    assert "short summary" in parent_prompt and "RAW-TOOL-DUMP" not in parent_prompt


# ---- 5.7 model routing ---------------------------------------------------------

@pytest.mark.parametrize("level,model", [("easy", "claude-haiku-5-5"), ("medium", "claude-sonnet-5-5"),
                                         ("hard", "claude-opus-5-5")])
def test_model_routing(level, model):
    mr = load("model_routing")
    fake = Fake(lambda k, kw: reply(parsed=mr.Difficulty(level=level)) if k == "parse" else reply("answer"))
    chosen, _ = mr.routed_answer(fake, "q", Budget())
    assert chosen == model and fake.calls[0][1]["model"] == mr.ROUTER_MODEL
    assert fake.calls[1][1]["model"] == model


def test_advisor_request_shape(capsys):
    mr = load("model_routing")
    block = NS(type="advisor_tool_result", content=NS(type="advisor_redacted_result"))
    fake = NS(beta=NS(messages=NS(create=lambda **kw: (fake.__dict__.setdefault("kw", kw),
                                                        reply(blocks=[block, NS(type="text", text="plan")]))[1])))
    mr.advisor_answer(fake, "task")
    tool = fake.kw["tools"][0]
    assert tool["type"] == "advisor_20260301" and tool["model"] == "claude-opus-5-5"
    assert fake.kw["betas"] == ["advisor-tool-2026-03-01"] and "tool_choice" not in fake.kw
    assert "advisor_redacted_result" in capsys.readouterr().out


# ---- 5.8 batch -----------------------------------------------------------------

def test_batch_requests_and_collect_by_custom_id():
    bj = load("batch_job")
    reqs = bj.build_requests({"a": "good", "b": "bad"})
    assert [r["custom_id"] for r in reqs] == ["a", "b"] and reqs[0]["params"]["model"] == bj.BATCH_MODEL

    def res(cid, rtype, text=""):
        msg = NS(content=[NS(type="text", text=text)])
        return NS(custom_id=cid, result=NS(type=rtype, message=msg))

    results = [res("b", "succeeded", " negative "), res("c", "expired"), res("a", "succeeded", "positive")]  # shuffled
    client = NS(messages=NS(batches=NS(results=lambda bid: iter(results))))
    assert bj.collect(client, "id") == {"a": "positive", "b": "negative", "c": "<expired>"}


def test_batch_wait_respects_deadline(monkeypatch):
    bj = load("batch_job")
    monkeypatch.setattr(bj.time, "sleep", lambda s: None)
    status = {"v": "in_progress"}
    batches = NS(retrieve=lambda bid: NS(processing_status=status["v"], request_counts=NS(processing=1)))
    client = NS(messages=NS(batches=batches))
    assert bj.wait(client, "id", timeout_s=0) is False  # deadline hit: caller can resume later
    status["v"] = "ended"
    assert bj.wait(client, "id", timeout_s=5) is True
