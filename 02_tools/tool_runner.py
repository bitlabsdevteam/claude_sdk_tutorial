"""2.4 Tool Runner: the SDK runs the loop; you write plain typed functions (beta helper)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from anthropic import beta_tool

from common.config import MODEL, make_client
from common.demo_tools import ToolError
from common.demo_tools import calculate as _calculate
from common.demo_tools import get_weather as _get_weather


# The schema is generated from the signature + docstring, so the docstring IS the tool description.
@beta_tool
def get_weather(location: str, unit: str = "celsius") -> str:
    """Get the current weather for one city (not a forecast).

    Args:
        location: City name, e.g. 'Paris'.
        unit: Either "celsius" or "fahrenheit".
    """
    try:
        return _get_weather(location, unit)
    except ToolError as e:
        # A raised exception is turned into an is_error tool_result by the runner;
        # returning the message keeps the recovery hint visible either way.
        raise ValueError(str(e)) from e


@beta_tool
def calculate(expression: str) -> str:
    """Evaluate an arithmetic expression using + - * / ** and numbers.

    Args:
        expression: e.g. '(3 + 4) * 2'.
    """
    try:
        return _calculate(expression)
    except ToolError as e:
        raise ValueError(str(e)) from e


def main() -> None:
    client = make_client()
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4096,
        tools=[get_weather, calculate],
        messages=[{"role": "user", "content": "What is the weather in London (celsius), and what is 2 ** 10?"}],
        max_iterations=8,  # still bound the loop even though the SDK drives it
    )
    last = None
    for message in runner:  # one iteration per API call; tools run between iterations
        last = message
        print(f"[turn] stop_reason={message.stop_reason} usage in={message.usage.input_tokens} out={message.usage.output_tokens}")
    if last is not None and last.stop_reason != "refusal":
        print("".join(b.text for b in last.content if b.type == "text"))


if __name__ == "__main__":
    main()
