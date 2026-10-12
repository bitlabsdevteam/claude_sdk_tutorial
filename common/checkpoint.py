"""Checkpointing and idempotent tool calls: survive a crash without losing work or repeating side effects.

Two separate mechanisms:
  RunStore - saves the conversation + budget at consistent boundaries, so a run can continue after a crash.
  Journal  - remembers the result of side-effecting tool calls, so replaying a turn does not repeat them.
"""
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Callable

from common.context import plain


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data)
    os.replace(tmp, path)  # atomic: a crash mid-write leaves the OLD file, never a half-written one


def _safe_id(run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", run_id):  # the id becomes a filename: no path tricks
        raise ValueError("run id must be letters, digits, _ or -")
    return run_id


class RunStore:
    def __init__(self, directory: Path | str, run_id: str):
        self.path = Path(directory) / f"{_safe_id(run_id)}.json"

    def save(self, messages: list, budget) -> None:
        """Call at consistent boundaries only (run_agent's `on_turn`): every tool_use must have its tool_result."""
        state = {"turns": budget.turns, "tokens": budget.tokens, "cost_usd": budget.cost_usd}
        # Blocks are stored exactly as returned (thinking blocks included), so a resumed history stays valid.
        content = [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else
                    [b if isinstance(b, dict) else plain(b) for b in m["content"]]} for m in messages]
        _atomic_write(self.path, json.dumps({"messages": content, "budget": state}))

    def load(self) -> tuple[list, dict] | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text())
        return data["messages"], data["budget"]


class Journal:
    """Results of side-effecting calls, keyed by tool name + canonical arguments.

    Right for "make this true" tools (write file X, create ticket titled T, send THIS email). Wrong for
    "do it again" semantics (increment, append): give those an explicit idempotency key argument instead.
    """

    def __init__(self, path: Path | str, side_effect_tools: set[str]):
        self.path, self.tools = Path(path), set(side_effect_tools)
        self.done: dict[str, list] = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.replayed = 0

    @staticmethod
    def key(name: str, args: dict) -> str:
        return hashlib.sha256(f"{name}:{json.dumps(args, sort_keys=True, default=str)}".encode()).hexdigest()[:16]

    def wrap(self, execute: Callable[[str, dict], tuple[str, bool]]) -> Callable[[str, dict], tuple[str, bool]]:
        def run(name: str, args: dict) -> tuple[str, bool]:
            if name not in self.tools:
                return execute(name, args)  # reads are safe to repeat
            k = self.key(name, args)
            if k in self.done:
                self.replayed += 1
                content, is_error = self.done[k]
                return content, is_error  # already happened: return the stored result, do NOT run it again
            content, is_error = execute(name, args)
            if not is_error:  # failures may be retried; only record completed effects
                self.done[k] = [content, is_error]
                _atomic_write(self.path, json.dumps(self.done))  # persisted BEFORE we return, so a crash keeps it
            return content, is_error
        return run
