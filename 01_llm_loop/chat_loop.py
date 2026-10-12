"""1.3 The loop: a chat REPL. The model is stateless, so we resend the whole history each turn."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, log_usage, make_client

client = make_client()
SYSTEM = "You are a concise, helpful assistant."
MAX_TURNS = 20  # bound the loop: history (and cost) grows every turn

messages: list[dict] = []

for _ in range(MAX_TURNS):
    user = input("you> ").strip()
    if user.lower() in {"", "exit", "quit"}:
        break

    messages.append({"role": "user", "content": user})
    # Stateless API: the model remembers nothing, so the ENTIRE history goes out on every call.
    # That is why input tokens (and cost) grow each turn.
    response = client.messages.create(
        model=MODEL, max_tokens=2048, system=SYSTEM, messages=messages
    )
    # Append the full content list back, not just the text: this keeps the history valid
    # once thinking and tool-use blocks appear in later levels.
    messages.append({"role": "assistant", "content": response.content})

    # Check stop_reason before trusting content: a refusal has no useful answer to show.
    if response.stop_reason == "refusal":
        print("claude> (declined to answer)")
        continue

    print("claude>", "".join(b.text for b in response.content if b.type == "text"))
    log_usage(response)
else:  # for/else: runs only if the loop was NOT ended by `break`
    print(f"(reached {MAX_TURNS} turns, stopping)")
