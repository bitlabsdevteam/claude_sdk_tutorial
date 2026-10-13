# Runbook

| Symptom | Check | Action |
|---|---|---|
| Run stopped `max_cost` / `max_turns` / `timeout` | Trace JSONL for the run id: turns, cost, repeated tools | Raise the limit only after reading the trace; a loop means fix the prompt/tool, not the budget |
| `stuck loop` / error spiral stop | `LoopGuard` events in the trace | Look at the failing tool's error text: usually a tool message that does not tell the model how to recover |
| Refund denied unexpectedly | `audit.jsonl` entry (`decision`, `reason`) | Above the auto limit with no human: route to the approval queue. Validation error: the ids/amount were wrong |
| Run crashed mid-ticket | `workdir/<run_id>.json` and `.journal.json` exist | Re-run `handle_ticket` with the same `workdir` and `run_id`: it resumes and replays journalled refunds instead of repeating them |
| Suspected injection | Trace events `denied`/`blocked`, audit log, ticket body | Escalate to security; add the ticket as a `red_team` case in `evals/ticket_ops.jsonl` |
| Release candidate | `python 07_enterprise_capstone/run_evals.py` | Ship only if the gate is OPEN; run `--live` (paid, ask first) before a model or prompt change |
| Over daily budget | Ledger / `cost_report.py` | Stop new runs (`Ledger.can_start`), investigate wasted spend |
