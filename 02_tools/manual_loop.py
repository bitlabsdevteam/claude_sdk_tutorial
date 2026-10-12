"""2.2 The manual tool loop: call, run the requested tools, return tool_results, repeat."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, log_usage, make_client
from common.demo_tools import TOOLS, run_tool

MAX_TURNS = 8  # agent loops must be bounded; a confused model could otherwise loop forever


def execute_sequentially(tool_uses: list) -> list[dict]:
    """Run each requested tool and build one tool_result per tool_use (matched by id)."""
    results = []
    for block in tool_uses:
        content, is_error = run_tool(block.name, block.input)  # block.input is already parsed
        results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
    return results


def run_loop(client, messages: list, tools: list, execute=execute_sequentially, max_turns: int = MAX_TURNS):
    """Loop until the model stops asking for tools. Returns the final response."""
    for _ in range(max_turns):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=tools,
            messages=messages,
            output_config={"effort": "low"},  # simple tool task; keep cost down
        )
        log_usage(response)

        if response.stop_reason != "tool_use":
            return response  # end_turn, refusal, max_tokens: caller inspects stop_reason

        # Append the assistant turn unchanged (this also keeps any thinking blocks valid).
        messages.append({"role": "assistant", "content": response.content})
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        # ALL results for this turn go back in ONE user message.
        messages.append({"role": "user", "content": execute(tool_uses)})
    raise RuntimeError(f"No final answer after {max_turns} turns")


def final_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text")


def main() -> None:
    client = make_client()
    messages = [{"role": "user", "content": "What is the weather in Tokyo (celsius), and what is 17 * 23?"}]
    response = run_loop(client, messages, TOOLS)
    if response.stop_reason == "refusal":
        print("Refused:", response.stop_details)
    else:
        print(final_text(response))


if __name__ == "__main__":
    main()
