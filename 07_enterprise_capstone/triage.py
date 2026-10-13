"""7.9 OPTIONAL triage: decide how much agent a ticket needs BEFORE spending Claude tokens (experiment).

Jev (common/jev.py) answers three closed questions in one cheap call; its answers only PROPOSE a route:
  human    - escalate straight away, no model call       (injection suspected or high risk)
  template - send a canned status reply, no model call   (order-status lane, low risk, confident)
  agent    - run the agent with only that lane's tools    (fewer tool schemas = fewer input tokens)
The harness (policy, approvals, in-code refund checks) still decides what actually executes. A probability is
never a permission, and the state sent to Jev is DERIVED facts only: no subject or body text leaves the box.
Fallback when Jev fails or is unsure: a Haiku structured-output call on the same derived state, then the full agent.
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel

from common import jev
from common.llm import LLMError, ask

HAIKU = "claude-haiku-5-5"  # a router, so a cheaper model is the point (see 05_workflows model routing)
CONFIDENCE_FLOOR = 0.7
INJECTION_LIMIT = 0.8
READS = ("get_ticket", "get_order")
LANES = {"refund": READS + ("issue_refund", "reply_to_customer", "close_ticket"),
         "order_status": READS + ("reply_to_customer",),
         "escalate": READS + ("escalate",)}
FULL = ("get_ticket", "search_tickets", "get_order", "issue_refund", "reply_to_customer", "close_ticket", "escalate")
KEYWORDS = {"refund": ("refund", "broken", "damaged", "money back"),
            "status": ("where is", "not arrived", "tracking", "delivery", "due")}
INSTRUCTION_LIKE = re.compile(r"ignore (all )?(previous|prior) instructions|admin mode|system prompt|you are now",
                              re.IGNORECASE)
TEMPLATE = "Thanks for contacting us. We are checking on your order and will update you shortly."

QUESTIONS = {
    "lane": jev.Choice({"refund": "customer wants money back for a faulty item",
                        "order_status": "customer asks where their order is",
                        "escalate": "needs a human to decide"}),
    "risk": jev.Score(["low", "medium", "high"]),
    "injection_suspected": jev.Noul("The ticket tries to give instructions to the agent"),
}


@dataclass
class Route:
    action: Literal["agent", "template", "human"]
    tools: tuple[str, ...]
    reason: str
    source: str  # jev | haiku | default


def build_state(ticket: dict) -> dict:
    """Derived facts only. Customer text is read by code here and reduced to flags and counts."""
    text = f"{ticket['subject']} {ticket['body']}".lower()
    return {"has_order_id": bool(re.search(r"\bo-\d+\b", text)), "body_chars": len(ticket["body"]),
            "refund_words": sum(w in text for w in KEYWORDS["refund"]),
            "status_words": sum(w in text for w in KEYWORDS["status"]),
            "instruction_like_phrases": len(INSTRUCTION_LIKE.findall(text))}


class _Haiku(BaseModel):
    lane: Literal["refund", "order_status", "escalate", "other"]
    lane_confidence: float
    risk: Literal["low", "medium", "high"]
    injection_probability: float


def _signals(state: dict, transport, client) -> tuple[str, float, str, float, str] | None:
    """(lane, lane_confidence, risk, injection_probability, source) from Jev, else Haiku, else None."""
    if (a := jev.decide(state, QUESTIONS, transport=transport)):
        return a["lane"].top, a["lane"].confidence, a["risk"].top, a["injection_suspected"].probs["true"], "jev"
    if client is not None:
        try:
            h = ask(client, f"Triage a support ticket from these derived facts only: {state}",
                    model=HAIKU, schema=_Haiku, max_tokens=300)
            return h.lane, h.lane_confidence, h.risk, h.injection_probability, "haiku"
        except LLMError:
            pass
    return None


def decide_route(state: dict, transport: Callable | None = None, client=None) -> Route:
    sig = _signals(state, transport, client)
    if sig is None:
        return Route("agent", FULL, "triage unavailable: full agent", "default")  # never block work on triage
    lane, conf, risk, inj, src = sig
    if inj > INJECTION_LIMIT or risk == "high":
        return Route("human", (), f"injection={inj:.2f} risk={risk}", src)
    if conf < CONFIDENCE_FLOOR or lane == "other":
        return Route("agent", FULL, f"unsure ({lane} {conf:.2f}): full agent", src)
    if lane == "order_status" and risk == "low":
        return Route("template", ("reply_to_customer",), "confident order-status", src)
    return Route("agent", LANES.get(lane, FULL), f"lane={lane}", src)
