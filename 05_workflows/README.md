# Level 5: Workflow patterns

Run from the project root with the venv active. A **workflow** is code you control that calls the model at fixed or bounded points. An **agent** (Level 3) lets the model choose every step. Prefer the simplest design that works: single call, then a workflow, then an agent.

| Script | Pattern | Use when | Don't use when |
|---|---|---|---|
| `chain.py` | Prompt chaining + gate | Ordered steps, each easier alone | One prompt already works |
| `router.py` | Routing | Distinct input categories | Categories overlap, or one prompt is fine |
| `parallel.py` | Sectioning, voting | Independent parts; unreliable single answers | Steps depend on each other |
| `orchestrator.py` | Orchestrator-workers | Sub-tasks unknown until run time | Sub-tasks are fixed (use sectioning) |
| `eval_opt.py` | Evaluator-optimizer | Clear rubric, feedback improves output | No rubric, or one pass is enough |
| `subagents.py` | Subagents + handoff | Sub-task would flood the parent's context | Sub-task is small |
| `model_routing.py` | Model routing, advisor | Mixed easy/hard traffic, measured | Not measured (try best model at low effort first) |
| `batch_job.py` | Message Batches (~50% off) | Offline, independent, can wait | A user is waiting |

Run any with `python 05_workflows/<name>.py`. `batch_job.py <batch_id>` resumes an earlier batch; `model_routing.py --advisor` also runs the advisor demo (beta).

Shared helpers: `common/llm.py` (`ask()`: text or a Pydantic object, checks `stop_reason`, records to a `Budget`) and `common/budget.py` (now thread-safe, with `absorb()` to roll sub-budgets into a parent). Tests: `pytest tests/05_workflows` (mocked). Parallel patterns make several paid calls per run; each run is capped by a `Budget`.

## Things to try

- In `chain.py`, make the gate stricter and watch step 2 never run.
- In `parallel.py`, vote with `n=1` vs `n=5`: what do you gain for the extra cost?
- In `eval_opt.py`, make the rubric impossible: `converged=False` shows why `MAX_ROUNDS` exists.
- In `subagents.py`, print the parent's prompt: it holds only the short handoffs, never the raw tool output.
- Compare `model_routing.py` against just running Opus at `effort="low"`.

## Checkpoint

Which pattern would you use for your own problem, and what simpler design did you rule out?

Work down the ladder: could one prompt do it? A fixed chain? Only if the steps truly can't be known in advance does an agent (Level 3) earn its extra cost and unpredictability.

## Next

Level 6: `06_harness/`.
