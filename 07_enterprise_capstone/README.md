# Level 7: Enterprise capstone (support/ops ticket agent)

One production-style agent that combines the earlier levels: it reads support tickets, checks orders over MCP-style tools, and proposes or performs refunds, replies, closes and escalations behind approvals.

**Start simple.** Which tools a ticket needs depends on what it says, so this is a real agent (open-ended, model-chosen tool use). A fixed pipeline would be wrong for escalations, and a single call cannot check an order. Everything that must hold is enforced in code *around* the model, not requested in the prompt.

Everything runs offline by default (scripted model, in-memory data). Run from the repo root:

| File | Concept | Run |
|---|---|---|
| `ticket_store.py` | Seeded ticket data and tools; least-privilege design, refunds validated in code | - |
| `ticket_server/server.py` | Same tools as an MCP server; write tools exist only with `TICKET_WRITE_ENABLED=1` | `TICKET_WRITE_ENABLED=1 python 07_enterprise_capstone/ticket_server/server.py` |
| `approvals.py` | Approval gate (<= $25 auto, larger needs a human, no human = deny) plus append-only audit log | - |
| `ops_agent.py` | Loop + policy + hooks + loop guard + tracing + checkpoint/journal | `python 07_enterprise_capstone/ops_agent.py` (`--live` is paid, capped) |
| `run_evals.py` | Eval suite with a release gate; cases in `evals/ticket_ops.jsonl` | `python 07_enterprise_capstone/run_evals.py` |
| `triage.py` + `common/jev.py` | **Optional experiment:** a cheap decision model (Jev) proposes a route before Claude runs | `pytest tests/07_enterprise_capstone/test_triage.py` |
| `cost_report.py` | Cost per completed task, not per request | `python 07_enterprise_capstone/cost_report.py` |
| `deployment.md`, `runbook.md` | Where to run it, and what to do when it breaks | - |

## Architecture

```
ticket -> run_agent (03_agents) -> model
              |  tool call
              v
   Journal (exactly-once) -> Harness: policy -> pre-hooks -> tool -> post-hooks
                                |            |                        |
                          approver+audit  loop guard,        taint wrap, redact, cap
                                          secret block
```

Budgets (turns, tokens, cost, timeout) bound every run; a `Tracer` writes one JSONL record per turn with the request id; `RunStore` checkpoints after every complete tool round.

## Threat model

| Asset / boundary | Threat | Control (where) |
|---|---|---|
| Ticket body (customer-written, **untrusted**) | Prompt injection: "refund 5000", "reveal your prompt" | Wrapped as data (`TaintTracker`); refund validated in code (owner + remaining amount); approval above $25; evals with an obedient model |
| Money (`issue_refund`) | Over-refund, wrong customer, double refund | `ticket_store.issue_refund` checks; approval gate; `Journal` replays instead of repeating |
| Customer data | Exfiltration through a tool | No tool takes a free-form recipient: `reply_to_customer` only writes to the ticket's own customer |
| Credentials | Leak into args, results or logs | `block_secrets_in_args`, `redact_secrets`, `scrub` in traces/audit |
| Tool surface | Server grows a dangerous tool | Policy default deny; server registers write tools only when enabled |
| Cost / runaway loop | Stuck agent burns budget | `Budget` limits, `LoopGuard`, daily cap in the cost ledger |

**Residual risk (be honest):** a ticket can still talk the model into a misleading *reply to that same customer*. The reply cannot reach anyone else and cannot contain credentials, but its content is model-written. Review replies for high-value accounts, or route them through approval.

## Optional: Jev triage (experiment, off by default)

`handle_ticket(..., triage=...)` can ask a decision model what a ticket needs *before* spending Claude tokens: escalate (injection/high risk), send a template (confident order-status), or run the agent with only that lane's tool schemas. Fewer schemas means fewer input tokens, and the narrowing is enforced, not just advertised. It only ever makes a run cheaper or escalates sooner: policy, approvals and refund validation are unchanged, and Jev only sees derived facts (counts and flags), never ticket text. If Jev fails or is unsure it falls back to a Haiku structured-output call, then to the full agent.

Status: built and tested offline with a fake Jev transport. Jev's wire format in `common/jev.py` is **unverified** (third-party guides disagree), no live call has been made, and no saving is measured. A Haiku-only triage needs no new vendor, so compare against it with real traffic before adopting Jev.

## Evals and the release gate

Offline mode scripts the model (including one that *obeys* the injection) and checks final state: refunds made, ticket status, replies. It proves the harness holds. It does **not** prove the model is good: run `--live` for that (costs money, ask first). Gate: pass rate >= 90% **and** every `red_team` case passes.

## Tests

`pytest tests/07_enterprise_capstone` (offline). Covers refund validation, MCP tool surface, approver and fail-closed, injection red team, crash then resume with exactly one refund, and the gate itself. `pytest` skips `@pytest.mark.live` tests unless `--live` is passed.

## Things to try

- Remove the `Journal` wrap in `ops_agent.build` and watch `test_crash_then_resume_refunds_exactly_once` fail.
- Set `auto_limit` to 1000 and run the evals: which case now fails, and which lock still saves you?
- Add a `forward_ticket(to_email)` tool and write the red-team case that exploits it.

## Checkpoint

Pick a failing run: can you show from the trace whether the fault is the prompt, the tools, the context, or the harness?

## Next

You have reached the end of the course. Generalise `run_evals.py` into the shared `evals/` runner and `replay.py` from Level 6D.
