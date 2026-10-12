"""1.5 Adaptive thinking and effort. Thinking text is omitted by default; opt in to a summary."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, log_usage, make_client

client = make_client()

response = client.messages.create(
    model=MODEL,
    max_tokens=16000,
    # adaptive: the model decides how much to think (budget_tokens is rejected on current models).
    # display="summarized" is opt-in; the default returns empty thinking text. Billing is the same either way.
    thinking={"type": "adaptive", "display": "summarized"},
    output_config={"effort": "low"},  # try low / medium / high and compare usage
    messages=[{"role": "user", "content": "A bat and ball cost $1.10; the bat costs $1 more. Ball price?"}],
)

for block in response.content:
    if block.type == "thinking":
        print("[thinking summary]", block.thinking)
    elif block.type == "text":
        print("[answer]", block.text)

log_usage(response)
