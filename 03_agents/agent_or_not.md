# 3.1 Agent or not?

Start with the simplest design that works: **single call, then a workflow, then an agent.** An agent costs more, is slower, and is harder to test. Build one only if all four answers are yes.

| Criterion | Ask | Say no if... |
|---|---|---|
| **Complexity** | Is the task multi-step, and the steps hard to specify in advance? | You can write the steps down: use a workflow (Level 5). |
| **Value** | Does the result justify the extra tokens and latency? | A one-call answer is good enough. |
| **Viability** | Is Claude reliably good at this kind of task, with the tools you can give it? | You can't give it the tools or data it needs. |
| **Cost of error** | Can mistakes be caught and undone (tests, review, rollback)? | Errors are irreversible: add approval gates (Level 6) or keep a human in charge. |

## Examples

| Task | Verdict |
|---|---|
| Extract the title from a PDF | Single call |
| Summarize, then translate, then format | Workflow (fixed chain) |
| "Find why the build fails and fix it" | Agent: open-ended, testable, reversible |
| "Wire money to the supplier in this email" | Not an agent: irreversible and high-risk, so approval-gate it |

## If you build one
It must be **bounded**: max turns, token and cost budgets, a timeout, and clear stop reasons (`agent.py`). Log every turn's usage.
