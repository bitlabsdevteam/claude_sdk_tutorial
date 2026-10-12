"""2.6 Server tools: Anthropic runs them (web search, code execution). You only declare them.

Usage: python 02_tools/server_tools.py [search|code]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, log_usage, make_client

DEMOS = {
    "search": {
        # web_search_20260209 has dynamic filtering built in, so do NOT also declare code_execution.
        "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
        "prompt": "What is the latest stable Python release? Answer in one sentence and name your source.",
    },
    "code": {
        "tools": [{"type": "code_execution_20260521", "name": "code_execution"}],
        "prompt": "Compute the standard deviation of [2, 4, 4, 4, 5, 5, 7, 9] by running code.",
    },
}
MAX_CONTINUATIONS = 4  # a long server-side turn can pause; cap how often we resume it


def run(client, prompt: str, tools: list):
    messages = [{"role": "user", "content": prompt}]
    for _ in range(MAX_CONTINUATIONS + 1):
        response = client.messages.create(
            model=MODEL, max_tokens=4096, tools=tools, messages=messages,
            output_config={"effort": "low"},
        )
        log_usage(response)
        if response.stop_reason != "pause_turn":
            return response
        # The server hit its iteration limit mid-turn: re-send the paused turn so it continues.
        # There is no tool_result to add; the server already ran everything itself.
        messages.append({"role": "assistant", "content": response.content})
    raise RuntimeError("Turn still paused after max continuations")


def show(response) -> None:
    if response.stop_reason == "refusal":
        print("Refused:", response.stop_details)
        return
    for block in response.content:
        if block.type == "text":
            print(block.text)
        elif block.type == "server_tool_use":
            print(f"[server tool] {block.name}: {block.input}")
        elif block.type == "web_search_tool_result":
            # Success is a list of results; an error is a single object (HTTP 200, no exception raised).
            if isinstance(block.content, list):
                for r in block.content:
                    print(f"[source] {r.title} - {r.url}")
            else:
                print(f"[search error] {block.content.error_code}")
        elif block.type == "bash_code_execution_tool_result":
            result = block.content
            if result.type == "bash_code_execution_result":
                print(f"[stdout] {result.stdout.strip()} (exit {result.return_code})")
            else:
                print(f"[code error] {result.error_code}")


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "search"
    if name not in DEMOS:
        sys.exit(f"Choose one of: {', '.join(DEMOS)}")
    show(run(make_client(), DEMOS[name]["prompt"], DEMOS[name]["tools"]))


if __name__ == "__main__":
    main()
