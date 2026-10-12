"""1.2 System prompts: same question, different behavior."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, log_usage, make_client

client = make_client()
QUESTION = "How do I read a JSON file?"

for system in [
    None,
    "You are a senior Python mentor. Answer with one short code example and one sentence of explanation.",
    "You are a pirate. Stay in character.",
]:
    # `system` is a top-level parameter, not a message. Omit it entirely when None
    # (passing system=None would be sent as null and be rejected).
    kwargs = {"system": system} if system else {}
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": QUESTION}],
        **kwargs,
    )
    print(f"--- system: {system!r}")
    # Pick the text block by type: with thinking on, content[0] may not be text.
    print(next(b.text for b in response.content if b.type == "text"))
    log_usage(response)
