"""Level 0: verify the environment with one Messages API call and print usage."""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

# Level 0 is deliberately self-contained (no `common/` import) so it works before anything else is set up.
load_dotenv()  # reads ANTHROPIC_API_KEY (and CLAUDE_MODEL) from .env

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")  # env override lets you switch models without editing code

client = Anthropic()  # picks up ANTHROPIC_API_KEY or an `ant auth login` profile; no key in code

response = client.messages.create(
    model=MODEL,
    max_tokens=256,  # required by the API; a hard cap on output length, and therefore on output cost
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)

# content is a list of blocks, and the first one may be a thinking block rather than text,
# so pick the text block by type instead of assuming content[0].
text = next((b.text for b in response.content if b.type == "text"), "(no text returned)")
print(text)
# stop_reason tells you WHY it stopped: end_turn = finished, max_tokens = cut off, refusal = declined.
print(f"stop_reason={response.stop_reason}")
# usage is what you are billed on; log it from the very first call.
print(f"input_tokens={response.usage.input_tokens} output_tokens={response.usage.output_tokens}")
