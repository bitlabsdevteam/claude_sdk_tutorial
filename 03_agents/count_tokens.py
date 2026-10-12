"""3.6 Token counting and context-window budgeting: measure before you send, decide explicitly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.budget import PRICES
from common.config import MODEL, make_client
from common.demo_tools import TOOLS

FALLBACK_WINDOW = 1_000_000


def context_window(client, model: str = MODEL) -> int:
    try:
        return client.models.retrieve(model).max_input_tokens or FALLBACK_WINDOW  # live capability lookup
    except Exception:  # listing is a nicety, not a reason to fail
        return FALLBACK_WINDOW


def count(client, messages: list, system: str | None = None, tools: list | None = None, model: str = MODEL) -> int:
    kwargs = {k: v for k, v in {"system": system, "tools": tools}.items() if v}
    return client.messages.count_tokens(model=model, messages=messages, **kwargs).input_tokens


def check_fits(client, messages: list, reserve_output: int = 8_000, **kw) -> tuple[int, bool]:
    """Returns (input_tokens, fits). Callers must chunk or summarize on False; never truncate silently."""
    used = count(client, messages, **kw)
    return used, used + reserve_output <= context_window(client)


def main() -> None:
    client = make_client()
    messages = [{"role": "user", "content": "Compare the weather in Paris and Tokyo."}]
    plain = count(client, messages)
    with_tools = count(client, messages, tools=TOOLS)
    print(f"prompt only: {plain} tokens | with tool definitions: {with_tools} tokens "
          f"(tools cost {with_tools - plain} on EVERY request)")
    used, ok = check_fits(client, messages, tools=TOOLS)
    in_price = PRICES.get(MODEL, PRICES["claude-opus-5-5"])[0]
    print(f"window={context_window(client):,} fits={ok} est_input_cost=${used * in_price / 1e6:.6f}")


if __name__ == "__main__":
    main()
