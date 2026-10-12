"""1.4 Streaming: print tokens as they arrive, then get the complete message."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, log_usage, make_client

client = make_client()

# Stream long outputs: tokens show up immediately, and long requests avoid HTTP timeouts.
with client.messages.stream(
    model=MODEL,
    max_tokens=4096,
    messages=[{"role": "user", "content": "Write a short story about a robot learning to cook."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)  # flush so characters appear as they arrive
    final = stream.get_final_message()  # same object messages.create() would return

print()
log_usage(final)
