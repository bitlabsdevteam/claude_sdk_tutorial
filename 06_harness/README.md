# Level 6: Harness engineering

The **harness** is everything around the model: the loop, tools, context, permissions, state, and observability. This level treats it as a product. It is built in batches; this README grows with each.

| Batch | Topics | Status |
|---|---|---|
| **6A Context** | budget, compaction, append-only history, cache architecture, just-in-time retrieval | Done |
| Tracing (6.17) | structured per-turn traces, triage | Done |
| **6B Tool surface** | tool surface, programmatic tools, sandbox, permissions, hooks | Done |
| **6C Control** | budgets, checkpointing, fallbacks, failure modes, long-horizon, injection defense | Done |
| 6D Measurement | eval sets, hill-climbing, replay | Planned |
| 6E Hosted | Managed Agents, Agent SDK comparison, scheduled runs | Planned |

## 6A: Context engineering

Run from the project root with the venv active.

| Script | Concept | Run |
|---|---|---|
| `context_budget.py` | Split a *working* budget across system, tools, history, retrieved data; name the lever to pull when over | `python 06_harness/context_budget.py` (offline) |
| `compaction.py` | Client-side "simple compaction": summarise everything into one message; what to keep and drop; never mid tool round | `python 06_harness/compaction.py` (1 small paid call) |
| `append_only.py` | Offline check that consecutive requests only append (step 1 of the preserved-thinking check) | `python 06_harness/append_only.py` (offline) |
| `cache_architecture.py` | Stable prefix first, volatile content appended last; audit a prompt for cache-busters | `python 06_harness/cache_architecture.py` (offline) |
| `jit_context.py` | Load detail on demand; a small catalog plus a `load_topic` tool | `python 06_harness/jit_context.py` (paid, budget-capped) |

Shared: `common/context.py` (`approx_tokens`, a rough offline estimate; use `count_tokens` for exact numbers, 3.6). Tests: `pytest tests/06_harness` (offline, no API calls).

### Key rules

- **Append-only.** Never edit an earlier turn, the system prompt, or the tools between requests. A thinking block is bound to the conversation that produced it; editing history breaks it (400 on enforced accounts) and always misses the cache. Replace each edit with its append-only form: a `role: "system"` message instead of a system edit, server-side compaction or context editing instead of deleting old turns.
- **Compaction resets the cache,** and thinking from before the summary is not carried forward, so the summary must say what to keep.
- **Test your own harness.** `append_only.binding_check_kwargs()` builds the request options for step 2 (a live run with `prefix_mismatch_behavior`), which turns any history edit into a visible error. Run it on a few real turns before shipping.

## Tracing and 6B: seeing and controlling every tool call

Every tool call flows through one place, `common/harness.py`: **policy, then pre-hooks, then the tool, then post-hooks, with a trace of all of it.** `Harness.execute` has the same shape as `run_agent`'s `execute`, so any loop from Level 3 gets it by passing `harness.execute`. `run_agent` also accepts an optional `tracer`.

| Item | Concept | Run |
|---|---|---|
| `tracing.py` + `common/tracing.py` | One JSON line per turn (tokens, cache, latency, tool calls, cost, request id); `summarize` and `triage` name the faulty layer | `python 06_harness/tracing.py` (offline: a healthy and a broken scripted run; `--live` for a real one) |
| `tool_surface.md` | Few general tools vs many narrow ones; when to promote an action to its own tool | read it |
| `programmatic_tools.py` | Claude calls your tool from code; big results never enter its context | `python 06_harness/programmatic_tools.py` (paid, budget-capped) |
| `sandbox/runner.py` | Run model-written Python with a timeout, scrubbed env, throwaway directory, capped output | `python 06_harness/sandbox/runner.py` (local, no API) |
| `permissions.py` | allow / ask / deny by tool and argument, default deny, destructive tools always need approval | `python 06_harness/permissions.py` (offline; `--live` asks you on stdin) |
| `hooks.py` | Block, rewrite, redact, audit around every call | `python 06_harness/hooks.py` (offline; `--live` for an agent run) |

Shared: `common/harness.py` (`Harness`, `Policy`, `Rule`, `Block`), `common/tracing.py` (`Tracer`, `summarize`, `triage`), `common/workspace_tools.py` (a confined file workspace for the demos). Traces are written to `.traces/` (git-ignored).

### Key rules

- **Enforce in the harness, not the prompt.** A prompt is a request; a policy is enforcement. The model can be wrong or manipulated, and the policy still says no.
- **Default deny, fail closed.** An unknown tool, or an "ask" with no approver, is refused. Destructive tools are never auto-approved.
- **Denials are tool errors**, with a reason, so the model can adapt instead of the loop crashing.
- **Log sizes and names, never raw tool data.** Traces get shared; tool output can hold secrets.
- **The sandbox is not a security boundary.** `sandbox/runner.py` stops accidents (loops, huge output, leaked env vars), not attackers: the network and the rest of your disk are still reachable. Use containers or a hosted sandbox for untrusted code.
- **Programmatic tool calling rules:** the tool needs `allowed_callers` and cannot be `strict`; the container id must be passed back; the reply may contain only `tool_result` blocks.

### Debugging with traces

`triage()` maps symptoms to layers: failing tools means the **tool** layer, input growing every turn or a low cache hit rate means **context**, denials and limit stops mean the **harness**, and `max_tokens` or `refusal` means the **model/prompt**. Run `tracing.py` and compare the healthy and broken runs.

## 6C: control and recovery

When things go wrong (a crash, a refusal, a stuck loop, a poisoned document, an overspend) the harness must cope. The offline demos use a scripted model (`common/scripted.py`), so they are free and deterministic; the scripted model decides from the *history*, like the real one, which makes crash/resume honest.

| Item | Concept | Run |
|---|---|---|
| `budgets.py` | Cost per **completed task** (failed spend counts), daily cap, effort per task type, the advisory API `task_budget` vs the hard `Budget` | `python 06_harness/budgets.py` (offline; `--live` makes one tiny paid call) |
| `checkpoint.py` | Crash in the middle of a tool round, resume, side effect happens exactly once | `python 06_harness/checkpoint.py` (offline) |
| `fallbacks.py` | Read refusals and fallback responses; `fallbacks: "default"`; client-side middleware for other platforms | `python 06_harness/fallbacks.py` (offline; `--live` one tiny call) |
| `failure_modes.py` | Stuck loop, error spiral, hallucinated success, and what the trace says about each | `python 06_harness/failure_modes.py` (offline) |
| `long_horizon.py` | Progress file, one feature at a time, harness-side verification, clean-state handoff between sessions | `python 06_harness/long_horizon.py` (offline; `--live` is paid) |
| `injection_defense.py` | Red team: an obedient model reads a poisoned file; the send is blocked by taint tracking | `python 06_harness/injection_defense.py` (offline) |

Shared: `common/guards.py` (`LoopGuard`, `TaintTracker`), `common/checkpoint.py` (`RunStore`, `Journal`), `common/scripted.py` (`RuleModel`). `run_agent` gained two optional arguments: `on_turn` (called at consistent boundaries, for checkpoints) and `stop_if` (a guard can end the run). Guards are `Harness` hooks, so they appear in traces and `triage()`.

### Key rules

- **Checkpoint only at consistent boundaries** (every `tool_use` has its `tool_result`). A resumed history must be valid, so save with `on_turn`, never mid-round. Write files atomically.
- **Make side effects idempotent.** On resume the model re-issues the interrupted round; the `Journal` returns the stored result instead of sending the email again. It keys by tool name plus arguments, so it fits "make this true" tools. For "do it again" tools (increment, append) give the tool an explicit idempotency key.
- **Refusals are not exceptions.** Check `stop_reason` before reading `content`; opt into `fallbacks: "default"`; if the whole chain refuses, stop gracefully and log the category. Never retry the same request in a loop, and don't show classifier details to users.
- **The model's "done" is a claim, not a fact.** Verify outcomes in the harness (`failure_modes.judge`, `long_horizon.finish_feature`).
- **Detect, warn, then stop.** `LoopGuard` first returns an error telling the model to change approach, then trips a hard stop. Repeated *identical* calls are the signal; changed arguments reset it.
- **Prompt injection: enforce, don't detect.** You cannot reliably spot a malicious instruction. You *can* stop a run that has read untrusted content from doing anything outward-facing. The cost is capability (a tainted run can't send), so the user continues in a fresh run or approves explicitly. Wrapping untrusted text in tags is only a soft hint. An approval gate alone is not enough, because people click yes; the demo shows taint tracking holding even when approval is auto-granted.
- **Cost is per completed task.** A cheap request that fails still cost money; `Ledger` counts it. The API `task_budget` is advisory pacing for the model; the `Budget` is the hard stop.

## Tests

`pytest tests/06_harness` (offline). Sandbox tests spawn short local Python subprocesses; nothing calls the API.

## Things to try

- In `context_budget.py`, change the working budget and watch which lever it suggests.
- In `append_only.py`, add a timestamp to the system prompt on turn 3 and see the violation.
- In `jit_context.py`, compare the up-front token estimate to the catalog size.
- In `permissions.py`, add a rule that lets `read_file` read only `*.md`, then check the walkthrough.
- In `hooks.py`, remove `block_secrets_in_args` and see the secret reach the file.
- In `tracing.py`, add a third scripted run that gets denied by policy and read its triage.

- In `injection_defense.py`, add a second untrusted source and a clean-run exception, and decide what you'd lose.
- In `checkpoint.py`, remove the `Journal` wrap and watch the email go out twice.
- In `failure_modes.py`, change `warn_after`/`stop_after` and see how early the run is stopped.

## Next

6D: measurement (an eval set, hill-climbing against it, replaying recorded transcripts).
