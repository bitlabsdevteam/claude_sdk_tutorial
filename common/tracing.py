"""Structured traces: one JSON record per model turn, plus events (denials, hook actions).

Log SIZES and NAMES, never raw tool arguments or output: traces get shared, and tool data can hold secrets.
Every record carries the API `request_id`, so a bad turn can be traced back to Anthropic's logs.
"""
import json
import re
import uuid
from collections import Counter
from pathlib import Path

SECRET = re.compile(r"sk-[A-Za-z0-9_-]{10,}|Bearer\s+\S+", re.IGNORECASE)


def scrub(value):
    """Defence in depth: even event details we chose to log must not carry credentials."""
    return SECRET.sub("[REDACTED]", value) if isinstance(value, str) else value


class Tracer:
    def __init__(self, path: Path | str | None = None, run_id: str | None = None):
        self.path = Path(path) if path else None
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.records: list[dict] = []

    def _write(self, record: dict) -> dict:
        record = {"run_id": self.run_id, **record}
        self.records.append(record)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:  # JSONL: append-only, one line per record, survives a crash
                f.write(json.dumps(record) + "\n")
        return record

    def turn(self, *, turn: int, model: str, response, latency_s: float, cost_usd: float, tools: list[dict]) -> dict:
        u = response.usage
        return self._write({
            "type": "turn", "turn": turn, "model": model, "stop_reason": response.stop_reason,
            "request_id": getattr(response, "_request_id", None),
            "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
            "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
            "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
            "latency_s": round(latency_s, 3), "cost_usd": round(cost_usd, 6),
            "tools": tools,  # [{name, is_error, duration_s, result_chars}]
        })

    def event(self, kind: str, **fields) -> dict:
        return self._write({"type": "event", "kind": kind, **{k: scrub(v) for k, v in fields.items()}})


def load(path: Path | str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def summarize(records: list[dict]) -> dict:
    """Where did the tokens, time and money go?"""
    turns = [r for r in records if r["type"] == "turn"]
    tool_calls = [t for r in turns for t in r["tools"]]
    read = sum(r["cache_read"] for r in turns)
    denom = read + sum(r["cache_write"] + r["input_tokens"] for r in turns)
    slowest = max(tool_calls, key=lambda t: t["duration_s"], default=None)
    return {
        "turns": len(turns),
        "input_tokens": sum(r["input_tokens"] for r in turns),
        "output_tokens": sum(r["output_tokens"] for r in turns),
        "cache_hit_rate": round(read / denom, 3) if denom else 0.0,
        "cost_usd": round(sum(r["cost_usd"] for r in turns), 6),
        "model_time_s": round(sum(r["latency_s"] for r in turns), 3),
        "tool_time_s": round(sum(t["duration_s"] for t in tool_calls), 3),
        "tool_calls": len(tool_calls),
        "tool_errors": sum(1 for t in tool_calls if t["is_error"]),
        "slowest_tool": (slowest["name"], slowest["duration_s"]) if slowest else None,
        "stop_reasons": [r["stop_reason"] for r in turns],
        "events": dict(Counter(r["kind"] for r in records if r["type"] == "event")),
    }


def triage(records: list[dict]) -> list[str]:
    """Point at the likeliest layer of a failing run: prompt/model, tools, context, or harness."""
    turns = [r for r in records if r["type"] == "turn"]
    if not turns:
        return ["no turns recorded"]
    s, found = summarize(records), []
    if s["tool_calls"] and s["tool_errors"] / s["tool_calls"] >= 0.5:
        found.append(f"TOOLS: {s['tool_errors']}/{s['tool_calls']} tool calls failed (check schemas and error messages)")
    first, last = turns[0]["input_tokens"] + turns[0]["cache_read"], turns[-1]["input_tokens"] + turns[-1]["cache_read"]
    if len(turns) > 2 and first and last / first >= 3:
        found.append(f"CONTEXT: input grew {last / first:.1f}x over {len(turns)} turns (compact or clear old results)")
    if len(turns) > 2 and s["cache_hit_rate"] < 0.2:
        found.append(f"CONTEXT: cache hit rate {s['cache_hit_rate']:.0%} (is the prefix changing between turns?)")
    denied = s["events"].get("denied", 0)
    if denied:
        found.append(f"HARNESS: {denied} call(s) denied by policy (is the policy too strict, or the prompt asking for it?)")
    if s["events"].get("blocked"):
        found.append(f"HARNESS: {s['events']['blocked']} call(s) blocked by a hook")
    if s["events"].get("loop_warning") or s["events"].get("loop_stop"):
        found.append("MODEL/HARNESS: the model repeated identical calls (stuck loop): fix the tool result or prompt")
    if s["events"].get("taint_block"):
        found.append(f"SECURITY: {s['events']['taint_block']} sensitive call(s) blocked after untrusted input (possible injection)")
    if turns[-1]["stop_reason"] in {"max_tokens", "refusal"}:
        found.append(f"MODEL/PROMPT: ended with stop_reason={turns[-1]['stop_reason']}")
    elif turns[-1]["stop_reason"] == "tool_use":
        found.append("HARNESS: run ended while the model still wanted tools (a limit stopped it)")
    return found or ["no obvious fault: read the turns"]
