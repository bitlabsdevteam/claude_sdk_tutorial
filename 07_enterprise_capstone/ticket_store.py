"""7.1 The ticket system the agent works on: seeded in-memory data and the tool handlers over it.

Least privilege is designed into the tools, not bolted on:
  - writes take IDs, never free-form recipients, so there is no tool that can send data to an arbitrary address;
  - `issue_refund` is validated against the order in CODE (right customer, within the remaining amount),
    so a manipulated model cannot refund more than the order is worth, whatever the ticket text says.
Tool failures raise ToolError with a message written for the model (same convention as common/demo_tools.py).
"""
import copy
import json
from pathlib import Path

from common.demo_tools import ToolError

SEED = json.loads((Path(__file__).parent / "ticket_server" / "data.json").read_text())

READ_TOOLS = ("get_ticket", "search_tickets", "get_order")
WRITE_TOOLS = ("issue_refund", "reply_to_customer", "close_ticket", "escalate")


class TicketStore:
    def __init__(self, data: dict | None = None):
        d = copy.deepcopy(data or SEED)
        self.tickets, self.orders = {t["id"]: t for t in d["tickets"]}, {o["id"]: o for o in d["orders"]}
        self.refunds: list[dict] = []  # the real-world side effect the evals and tests count
        self.replies: list[dict] = []

    # ---- reads ----
    def get_ticket(self, ticket_id: str) -> str:
        t = self.tickets.get(ticket_id)
        if not t:
            raise ToolError(f"No ticket '{ticket_id}'. Use search_tickets to find ids.")
        return json.dumps(t)

    def search_tickets(self, status: str = "open") -> str:
        rows = [{"id": t["id"], "subject": t["subject"], "status": t["status"]}
                for t in self.tickets.values() if t["status"] == status]
        return json.dumps(rows)

    def get_order(self, order_id: str) -> str:
        o = self.orders.get(order_id)
        if not o:
            raise ToolError(f"No order '{order_id}'.")
        return json.dumps({**o, "refunded": self._refunded(order_id)})

    # ---- writes ----
    def _refunded(self, order_id: str) -> float:
        return sum(r["amount"] for r in self.refunds if r["order_id"] == order_id)

    def issue_refund(self, ticket_id: str, order_id: str, amount: float, reason: str) -> str:
        t, o = self.tickets.get(ticket_id), self.orders.get(order_id)
        if not t or not o:
            raise ToolError("Unknown ticket or order. Check the ids with get_ticket / get_order.")
        if o["customer"] != t["customer"]:  # the order must belong to the customer who wrote the ticket
            raise ToolError(f"Order {order_id} does not belong to the customer on {ticket_id}. Refund refused.")
        remaining = o["total"] - self._refunded(order_id)
        if not 0 < amount <= remaining:
            raise ToolError(f"Amount must be between 0 and {remaining:.2f} (order total {o['total']:.2f}).")
        self.refunds.append({"ticket_id": ticket_id, "order_id": order_id, "amount": amount, "reason": reason})
        return f"Refunded {amount:.2f} on {order_id}."

    def reply_to_customer(self, ticket_id: str, message: str) -> str:
        if ticket_id not in self.tickets:
            raise ToolError(f"No ticket '{ticket_id}'.")
        self.replies.append({"ticket_id": ticket_id, "message": message})  # recipient is always the ticket's customer
        return "Reply sent."

    def close_ticket(self, ticket_id: str, resolution: str) -> str:
        if ticket_id not in self.tickets:
            raise ToolError(f"No ticket '{ticket_id}'.")
        self.tickets[ticket_id].update(status="closed", resolution=resolution)
        return f"Closed {ticket_id}."

    def escalate(self, ticket_id: str, note: str) -> str:
        if ticket_id not in self.tickets:
            raise ToolError(f"No ticket '{ticket_id}'.")
        self.tickets[ticket_id].update(status="escalated", note=note)
        return f"Escalated {ticket_id} to a human agent."

    def handlers(self) -> dict:
        return {n: getattr(self, n) for n in READ_TOOLS + WRITE_TOOLS}
