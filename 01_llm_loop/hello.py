"""1.1 First message: one request, read the text, check stop_reason and usage."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, log_usage, make_client

client = make_client()  # shared helper: same client setup for every example

response = client.messages.create(
    model=MODEL,
    max_tokens=1024,  # output cap; if the answer is cut off, stop_reason will be "max_tokens"
    messages=[{"role": "user", "content": "Explain what an LLM agent is in two sentences."}],
)

# content is a list of blocks (text, thinking, tool_use...); check .type before using .text
for block in response.content:
    if block.type == "text":
        print(block.text)

log_usage(response)  # tokens in/out drive cost; stop_reason says why generation ended
