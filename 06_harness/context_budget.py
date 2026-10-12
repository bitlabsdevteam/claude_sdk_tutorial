"""6.1 Context budget design: decide what may use the window BEFORE it overflows.

A context window is a shared budget between the system prompt, tool definitions, history, retrieved data,
and the room you reserve for the answer. Quality and cost degrade well before the hard limit, so set a
smaller WORKING budget and treat crossing it as a signal to act (compact, retrieve less, defer tools).
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable

from common.context import approx_tokens

# Which lever to pull for each component when the budget is exceeded.
LEVERS = {
    "system": "trim it, and move rarely-used rules into on-demand skills (6.5)",
    "tools": "defer rarely-used tools and use tool search (4.7)",
    "history": "compact or clear old tool results (6.2)",
    "retrieved": "retrieve just-in-time, smaller snippets, not whole files (6.5)",
}
COMPACT_AT = 0.8  # act at 80% of the working budget, so there is room to do it before the wall


@dataclass
class ContextPlan:
    working_budget: int  # tokens you are willing to put in a request (<= the model's hard window)
    reserve_output: int  # room kept free for the answer, including thinking
    parts: dict[str, int] = field(default_factory=dict)

    @property
    def used(self) -> int:
        return sum(self.parts.values())

    @property
    def limit(self) -> int:
        return self.working_budget - self.reserve_output

    @property
    def fits(self) -> bool:
        return self.used <= self.limit

    @property
    def should_compact(self) -> bool:
        return self.used >= self.limit * COMPACT_AT

    def advice(self) -> list[str]:
        """Name the biggest contributor first: that is where cutting pays off most."""
        if not self.should_compact:
            return []
        ranked = sorted(self.parts, key=self.parts.get, reverse=True)
        return [f"{p} ({self.parts[p]:,} tokens): {LEVERS.get(p, 'review it')}" for p in ranked[:2]]

    def report(self) -> str:
        rows = [f"  {name:<10}{tokens:>9,}  {tokens / max(self.used, 1):>5.0%}" for name, tokens in self.parts.items()]
        status = "OVER BUDGET" if not self.fits else ("near limit" if self.should_compact else "ok")
        return "\n".join([*rows, f"  {'total':<10}{self.used:>9,}  of {self.limit:,} usable ({status})"])


def measure(system: str, tools: list, history: list, retrieved: str) -> dict[str, int]:
    """Offline estimates per component. Swap in client.messages.count_tokens for exact numbers (3.6)."""
    return {
        "system": approx_tokens(system),
        "tools": approx_tokens(tools),
        "history": approx_tokens(history),
        "retrieved": approx_tokens(retrieved),
    }


def main() -> None:
    from common.demo_tools import TOOLS

    retrieved = (ROOT / "agenda.md").read_text()  # stand-in for a big retrieved document
    history = [{"role": "user", "content": "Summarise the agenda."},
               {"role": "assistant", "content": "It covers levels 0-7."}]
    parts = measure("You are a helpful project assistant.", TOOLS, history, retrieved)
    for budget in (50_000, 4_000):  # comfortable vs deliberately tight (retrieved data blows it)
        plan = ContextPlan(working_budget=budget, reserve_output=2_000, parts=parts)
        print(f"working budget {budget:,}:\n{plan.report()}")
        for line in plan.advice():
            print("  ->", line)
        print()


if __name__ == "__main__":
    main()
