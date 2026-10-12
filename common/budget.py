"""Budget for bounded agent loops: turns, tokens, estimated cost, and wall-clock time."""
import threading
import time
from dataclasses import dataclass, field

# USD per 1M tokens (input, output, cache read). Estimates only: check the pricing page before trusting them.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
CACHE_WRITE_MULTIPLIER = 1.25  # 5-minute cache writes cost 1.25x input


def estimate_cost(usage, model: str) -> float:
    inp, out, cache_read = PRICES.get(model, PRICES["claude-opus-5-5"])
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_hit = getattr(usage, "cache_read_input_tokens", 0) or 0
    return (
        usage.input_tokens * inp
        + cache_write * inp * CACHE_WRITE_MULTIPLIER
        + cache_hit * cache_read
        + usage.output_tokens * out
    ) / 1_000_000


@dataclass
class Budget:
    # Limits: any one of them ends the run. Several are used because each catches a different failure
    # (a loop that never stops, a runaway context, an expensive model, a hung tool or request).
    max_turns: int = 10
    max_total_tokens: int = 100_000  # input + output + cache tokens, summed over all turns
    max_cost_usd: float = 0.50
    timeout_s: float = 120.0
    # Running totals, updated by record().
    turns: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    # monotonic clock: immune to system clock changes, so the deadline can't move backwards.
    started: float = field(default_factory=time.monotonic)
    # Parallel workflows (Level 5) record from several threads; += on shared ints is not atomic.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def remaining_s(self) -> float:
        return self.timeout_s - (time.monotonic() - self.started)

    def record(self, usage, model: str) -> None:
        tokens = (
            usage.input_tokens
            + usage.output_tokens
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
            + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        )
        cost = estimate_cost(usage, model)
        with self._lock:
            self.turns += 1
            self.tokens += tokens
            self.cost_usd += cost

    def absorb(self, other: "Budget") -> None:
        """Fold a sub-budget's spend into this one, so a workflow reports cost per completed task."""
        with self._lock:
            self.turns += other.turns
            self.tokens += other.tokens
            self.cost_usd += other.cost_usd

    def exceeded(self) -> str | None:
        """Name of the first limit that is used up, or None. Checked before every API call."""
        if self.turns >= self.max_turns:
            return "max_turns"
        if self.tokens >= self.max_total_tokens:
            return "max_tokens"
        if self.cost_usd >= self.max_cost_usd:
            return "max_cost"
        if self.remaining_s() <= 0:
            return "timeout"
        return None
