"""3.5 Prompt caching: keep a big stable prefix first, then verify cache_read_input_tokens > 0."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.budget import estimate_cost
from common.config import MODEL, make_client

ROOT = Path(__file__).resolve().parents[1]


def stable_prefix() -> str:
    # Deterministic text only: a timestamp, UUID or unsorted dict here would silently bust the cache.
    docs = [ROOT / "agenda.md", ROOT / "CLAUDE.md", ROOT / "02_tools" / "tool_design.md"]
    return "You answer questions about this project.\n\n" + "\n\n".join(p.read_text() for p in docs)


def ask(client, system: str, question: str):
    return client.messages.create(
        model=MODEL,
        max_tokens=512,
        cache_control={"type": "ephemeral"},  # caches the last cacheable block (the system prompt here)
        system=system,  # render order is tools -> system -> messages, so stable goes first
        messages=[{"role": "user", "content": question}],  # volatile part goes last
        output_config={"effort": "low"},
    )


def report(label: str, response) -> None:
    u = response.usage
    print(f"{label}: uncached_in={u.input_tokens} cache_write={u.cache_creation_input_tokens or 0} "
          f"cache_read={u.cache_read_input_tokens or 0} out={u.output_tokens} ~${estimate_cost(u, MODEL):.4f}")


def main() -> None:
    client, system = make_client(), stable_prefix()
    r1 = ask(client, system, "In one sentence, what does Level 2 cover?")
    report("call 1", r1)  # expect cache_write > 0
    r2 = ask(client, system, "In one sentence, what does Level 5 cover?")
    report("call 2", r2)  # expect cache_read > 0 and a lower cost
    if not (r2.usage.cache_read_input_tokens or 0):
        print("No cache hit. The prefix may be below the model's minimum cacheable size, "
              "something in it changed between calls, or the 5-minute TTL expired.")


if __name__ == "__main__":
    main()
