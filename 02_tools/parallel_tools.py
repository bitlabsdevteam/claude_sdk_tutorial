"""2.3 Parallel tool calls and is_error: run independent calls concurrently, report failures to the model."""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable
sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the loop from 2.2

from manual_loop import final_text, run_loop

from common.config import make_client
from common.demo_tools import TOOLS, run_tool


def execute_in_parallel(tool_uses: list) -> list[dict]:
    """The model may emit several tool_use blocks in one turn; they are independent, so run them together."""

    def one(block):
        content, is_error = run_tool(block.name, block.input)
        # is_error=True tells the model the call failed, so it can retry or explain instead of guessing.
        return {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error}

    with ThreadPoolExecutor(max_workers=max(1, len(tool_uses))) as pool:
        return list(pool.map(one, tool_uses))  # map keeps order; ids make order irrelevant anyway


def main() -> None:
    client = make_client()
    # "Atlantis" fails on purpose: watch the model recover from the is_error result.
    messages = [{
        "role": "user",
        "content": "Compare the weather in Paris, Tokyo, London and Atlantis (celsius). Call tools in parallel.",
    }]
    response = run_loop(client, messages, TOOLS, execute=execute_in_parallel)
    print(final_text(response))
    # Each tool_result user message in `messages` holds every result for one assistant turn.
    print(f"[turns] {len(messages)} messages in history")


if __name__ == "__main__":
    main()
