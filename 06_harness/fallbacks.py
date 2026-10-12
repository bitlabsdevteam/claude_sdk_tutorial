"""6.13 Refusals and fallbacks: a safety classifier may decline a request. Handle it, don't crash or loop.

A refusal is a normal HTTP 200 with `stop_reason == "refusal"`, not an exception. Two layers of defence:
  1. Server-side `fallbacks`: the API re-runs a declined request on another model in the same call.
  2. Your code: if the whole chain refuses, stop gracefully (never retry the same request in a loop).

Offline demo of how to read each kind of response (free): `python 06_harness/fallbacks.py`
`--live` sends one ordinary request with fallbacks enabled (tiny, paid) so you can see the request shape work.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, make_client

BETA = "server-side-fallback-2026-07-01"  # the "default" form needs this header; the array form needs -06-01


def request_kwargs() -> dict:
    """Extra args for `client.beta.messages.create`. "default" lets Anthropic pick the substitute by refusal
    category, so you never maintain a model list that goes stale."""
    return {"betas": [BETA], "fallbacks": "default"}


@dataclass
class Outcome:
    status: str  # ok | fallback_served | refused
    text: str = ""
    served_by: str | None = None
    switches: list[tuple[str, str]] = field(default_factory=list)  # (declined model, model that continued)
    category: str | None = None  # why it was declined, when refused


def interpret(response) -> Outcome:
    """Check stop_reason BEFORE reading content, then report whether a fallback model served the answer."""
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        return Outcome("refused", category=getattr(details, "category", None), served_by=getattr(response, "model", None))
    switches = [(b.from_.model, b.to.model) for b in response.content if b.type == "fallback"]
    iterations = getattr(response.usage, "iterations", None) or []
    ran = any(getattr(e, "type", None) == "fallback_message" for e in iterations)  # covers sticky turns too
    text = "".join(b.text for b in response.content if b.type == "text")
    return Outcome("fallback_served" if switches or ran else "ok", text, getattr(response, "model", None), switches)


def user_message(outcome: Outcome) -> str:
    """What the END USER sees. Don't expose classifier internals; do log the category for yourself."""
    if outcome.status == "refused":
        return "Sorry, I can't help with that request."
    return outcome.text


def middleware_client():
    """For platforms without server-side fallbacks (Bedrock, Vertex, Foundry): retry client-side instead.

    Share ONE state across a conversation so later turns stay on the model that accepted. Not called in the
    demo: it needs a real provider setup. `with state:` must wrap every request that shares the pin."""
    import anthropic
    from anthropic.lib.middleware import BetaFallbackState, BetaRefusalFallbackMiddleware

    client = anthropic.Anthropic(middleware=[BetaRefusalFallbackMiddleware([{"model": "claude-opus-4-8"}])])
    return client, BetaFallbackState()


def demo() -> None:
    declined = NS(stop_reason="refusal", content=[], model="claude-opus-5-5", usage=NS(iterations=None),
                  stop_details=NS(category="cyber"))
    served = NS(stop_reason="end_turn", model="claude-opus-4-8", usage=NS(iterations=[NS(type="fallback_message")]),
                content=[NS(type="fallback", from_=NS(model="claude-opus-5-5"), to=NS(model="claude-opus-4-8")),
                         NS(type="text", text="Here is a safe answer.")], stop_details=None)
    normal = NS(stop_reason="end_turn", model="claude-opus-5-5", usage=NS(iterations=None),
                content=[NS(type="text", text="Hello!")], stop_details=None)
    for label, response in [("normal", normal), ("fallback served", served), ("whole chain refused", declined)]:
        o = interpret(response)
        print(f"{label:>20}: status={o.status} served_by={o.served_by} switches={o.switches} category={o.category}")
        print(f"{'':>20}  user sees: {user_message(o)!r}")


def live() -> None:
    response = make_client().beta.messages.create(
        model=MODEL, max_tokens=200, output_config={"effort": "low"}, **request_kwargs(),
        messages=[{"role": "user", "content": "Say hello in five words."}])
    o = interpret(response)
    print(f"status={o.status} served_by={o.served_by} text={o.text!r}")


if __name__ == "__main__":
    live() if "--live" in sys.argv else demo()
