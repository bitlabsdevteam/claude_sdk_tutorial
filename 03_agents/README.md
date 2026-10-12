# Level 3: Agents

Run from the project root with the venv active. An agent is a tool loop the model steers; the harness around it (limits, memory, context) is what makes it safe. Start simple: a single call, then a workflow, then an agent only if `agent_or_not.md` says yes.

| Script | Concept | Run |
|---|---|---|
| `agent_or_not.md` | Four-criteria check | read it |
| `agent.py` | **Bounded loop**: turns, tokens, cost, timeout, stop reasons | `python 03_agents/agent.py` |
| `research_agent.py` | Read-only file research agent (4 tools, confined to the repo) | `python 03_agents/research_agent.py "question"` |
| `memory_agent.py` | Durable notes and a resumable session | `python 03_agents/memory_agent.py demo "I like Python"` |
| `caching.py` | Stable prefix first; verify `cache_read_input_tokens` | `python 03_agents/caching.py` |
| `count_tokens.py` | `count_tokens` and window budgeting | `python 03_agents/count_tokens.py` |
| `long_context.py` | Context editing vs compaction (beta) | `python 03_agents/long_context.py` |
| `planner.py` | Todo plan, run-tests-then-fix, harness-side verification | `python 03_agents/planner.py` |
| `choose_approach.md` | Manual loop vs Tool Runner vs Managed Agents vs Agent SDK | read it |

Shared: `common/budget.py` (`Budget`, cost estimates). Tests: `pytest tests/03_agents` (mocked). Every demo makes paid calls; each is capped by its `Budget`.

## Things to try

- In `agent.py`, set `max_turns=1` and watch the `max_turns` stop. Then set a tiny `max_cost_usd`.
- Run `memory_agent.py` twice with the same session name, then with a new one: notes persist, history doesn't.
- Run `caching.py` twice within 5 minutes and compare `cache_read`.
- In `planner.py`, remove the harness-side test run and ask: would you trust the model's claim?

## Checkpoint

How do you guarantee your agent loop terminates and stays within budget?

Every iteration checks hard limits *before* the next API call (turns, tokens, cost, deadline), requests carry a timeout, and the loop returns an explicit stop reason instead of raising. The limits live in the harness, never in the prompt.

## Next

Level 4: `04_mcp/`.
