"""One-shot LLM call helper for workflows: text or a validated object, with budget and stop_reason checks."""
from common.budget import Budget
from common.config import MODEL


class LLMError(Exception):
    """The model refused, was cut off, or the budget is spent. Workflows catch this to stop cleanly."""


def ask(client, prompt: str, *, system: str | None = None, model: str = MODEL, schema=None,
        budget: Budget | None = None, max_tokens: int = 2048, effort: str = "low"):
    """Returns text, or a parsed `schema` (Pydantic class) instance when `schema` is given."""
    if budget and (limit := budget.exceeded()):
        raise LLMError(f"budget exceeded: {limit}")  # checked BEFORE spending, like the agent loop

    kwargs = {"system": system} if system else {}
    common = dict(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}],
                  output_config={"effort": effort}, **kwargs)
    if schema:
        response = client.messages.parse(output_format=schema, **common)  # SDK merges format into output_config
    else:
        response = client.messages.create(**common)

    if budget:
        budget.record(response.usage, model)
    # Check stop_reason before trusting content.
    if response.stop_reason == "refusal":
        raise LLMError("model refused")
    if response.stop_reason == "max_tokens":
        raise LLMError("output truncated: raise max_tokens")
    if schema:
        return response.parsed_output
    return "".join(b.text for b in response.content if b.type == "text")
