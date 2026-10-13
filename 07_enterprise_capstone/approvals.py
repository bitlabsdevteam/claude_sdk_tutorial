"""7.4 Approval gate and audit log for destructive actions.

Policy (common/harness.py) sends every destructive tool to "ask"; this is the asker. Rules, in order:
  1. Non-money writes and refunds up to auto_limit are auto-approved (and logged). The refund itself is also
     validated in code (ticket_store.py), so approval is a second lock, not the only one.
  2. Larger refunds need a human.
  3. No human available means deny (fail closed).
Every decision is appended to an audit log: who decided, what, when, run id. Values that could hold secrets
are scrubbed; the free-text arguments themselves are not stored, only names and the amount.
"""
import json
import time
from pathlib import Path
from typing import Callable

from common.tracing import scrub


class AuditLog:
    def __init__(self, path: Path | str | None, run_id: str):
        self.path, self.run_id = Path(path) if path else None, run_id
        self.entries: list[dict] = []

    def record(self, tool: str, args: dict, decision: str, by: str, reason: str = "") -> None:
        entry = {"ts": round(time.time(), 3), "run_id": self.run_id, "tool": tool, "decision": decision, "by": by,
                 "ticket_id": args.get("ticket_id"), "order_id": args.get("order_id"), "amount": args.get("amount"),
                 "reason": scrub(reason)}
        self.entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:  # append-only JSONL
                f.write(json.dumps(entry) + "\n")


def make_approver(audit: AuditLog, human: Callable[[str, dict], bool] | None = None, auto_limit: float = 25.0):
    def approve(name: str, args: dict) -> bool:
        low_risk = name != "issue_refund" or float(args.get("amount", 0) or 0) <= auto_limit
        if low_risk:
            audit.record(name, args, "approved", "auto", f"within auto limit {auto_limit}")
            return True
        why = f"amount above {auto_limit}"
        if human is None:
            audit.record(name, args, "denied", "system", f"needs a human ({why}); none available")
            return False
        ok = bool(human(name, args))
        audit.record(name, args, "approved" if ok else "denied", "human", why)
        return ok
    return approve
