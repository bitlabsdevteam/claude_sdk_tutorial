"""A deterministic stand-in for the model, for free offline demos and tests.

RuleModel decides each reply from how many tool rounds the HISTORY already holds, exactly like the real model
(which only sees `messages`). That is what makes crash/resume demos honest: resume from saved history and the
model continues from the right step.
"""
from types import SimpleNamespace


class Blk(SimpleNamespace):
    """A content block with attribute access (like SDK blocks) and `model_dump` (so it can be checkpointed)."""

    def model_dump(self, **_):
        return dict(vars(self))


def tool_use(id_: str, name: str, **inp) -> Blk:
    return Blk(type="tool_use", id=id_, name=name, input=inp)


def text(t: str) -> Blk:
    return Blk(type="text", text=t)


def _rounds(messages: list) -> int:
    """Completed tool rounds = user messages made of tool_result blocks."""
    count = 0
    for m in messages:
        c = m["content"]
        if m["role"] == "user" and not isinstance(c, str) and c and all(
                (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_result" for b in c):
            count += 1
    return count


class RuleModel:
    """`script[k]` is the list of blocks to reply with after k completed tool rounds (last entry repeats).
    A reply containing a tool_use stops with "tool_use", otherwise "end_turn"."""

    def __init__(self, script: list[list], tokens: tuple[int, int] = (200, 30)):
        self.script, self.tokens, self.messages, self.calls = script, tokens, self, 0

    def create(self, **kw):
        self.calls += 1
        blocks = self.script[min(_rounds(kw["messages"]), len(self.script) - 1)]
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        usage = SimpleNamespace(input_tokens=self.tokens[0], output_tokens=self.tokens[1],
                                cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return SimpleNamespace(stop_reason=stop, content=blocks, usage=usage, _request_id=f"req_rule{self.calls:03d}",
                               stop_details=None)
