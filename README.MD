# claude_sdk_tutorial

A progressive, hands-on course for building **agentic solutions with the Claude API** (the official `anthropic` Python SDK), from a first API call up to harness engineering and an enterprise-style capstone.

Every module has a runnable example, a short README (concept, how to run, what to try next), and mocked tests that cost nothing to run. The curriculum itself lives in [`agenda.md`](agenda.md).

## Progress

| Level | Folder | Topics | Status |
|---|---|---|---|
| 0 Setup | [`00_setup/`](00_setup) | Env, API key, hello world, usage | Done |
| 1 The LLM loop | [`01_llm_loop/`](01_llm_loop) | System prompts, chat loop, streaming, thinking, structured outputs, errors | Done |
| 2 Tools | [`02_tools/`](02_tools) | Tool definitions, manual loop, parallel calls, Tool Runner, server tools, documents | Done |
| 3 Agents | [`03_agents/`](03_agents) | Bounded loop, memory, prompt caching, token counting, context editing, planning | Done |
| 4 MCP | [`04_mcp/`](04_mcp) | MCP server and client, connector, HTTP auth, tool search, security | Done |
| 5 Workflows | [`05_workflows/`](05_workflows) | Chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, subagents, model routing, batches | Done |
| 6 Harness engineering | [`06_harness/`](06_harness) | Context engineering, permissions, hooks, budgets, tracing, evals | In progress (context, tracing, tool safety, control and recovery done) |
| 7 Capstone | `07_enterprise_capstone/` | Production-style agent with MCP tools, approvals, tracing, evals | Built |

Start simple: a single call first, then a workflow, and an agent only when the task needs open-ended, model-driven tool use.

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then add your ANTHROPIC_API_KEY
python 00_setup/hello.py        # one real API call to verify your setup
pytest                          # mocked tests, no API calls
```

The SDK also works with an `ant auth login` profile, so the key in `.env` is optional if you use one. Never commit `.env`; it is git-ignored.

## Cost and safety

- Most examples make **real, paid API calls**. Agent and workflow demos are capped by a `Budget` (turns, tokens, cost, timeout), but read a script before you run it.
- The default model is `claude-opus-5-5`. Override it with the `CLAUDE_MODEL` env var. Only the model-routing and batch examples use cheaper models on purpose.
- All tests are mocked and make no API calls.

## Layout

```
agenda.md           curriculum and folder structure (source of truth)
CLAUDE.md           project conventions for working with Claude Code
common/             shared config, Budget, llm helper, demo tools
00_setup/ ... 07_enterprise_capstone/   one folder per level, each with its own README
tests/              mirrors the level folders
```

Each level folder is self-contained and may import from `common/`.

## Conventions

- Official `anthropic` SDK only; adaptive thinking; streaming for long outputs.
- Agent loops are always bounded and log per-turn usage.
- Tool output is treated as untrusted data; destructive actions need approval gates (Level 6).
- Check `stop_reason`, including `"refusal"`, before reading a response.

See [`CLAUDE.md`](CLAUDE.md) for the full list.
