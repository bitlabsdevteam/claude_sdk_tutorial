"""2.1 Defining tools: a JSON schema the model can call. Claude only *asks* to run it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, log_usage, make_client
from common.demo_tools import TOOLS


def main() -> None:
    client = make_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        tools=TOOLS,  # strict=True tools: input is guaranteed to match the schema
        # tool_choice stays "auto": forced choice 400s on current models, so steer in the prompt.
        messages=[{"role": "user", "content": "What's the weather in Paris in celsius? Use the get_weather tool."}],
    )

    if response.stop_reason == "refusal":
        print("Refused:", response.stop_details)
        return

    # stop_reason == "tool_use" means: the model wants YOU to run something. Nothing has run yet.
    print("stop_reason:", response.stop_reason)
    for block in response.content:
        if block.type == "tool_use":
            print(f"tool_use id={block.id} name={block.name} input={block.input}")  # input is already a dict
    log_usage(response)


if __name__ == "__main__":
    main()
