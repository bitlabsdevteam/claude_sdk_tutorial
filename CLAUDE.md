# CLAUDE.md

## Project purpose

A progressive learning and reference project for building **agentic solutions with the Claude API / Anthropic SDK**, from beginner to advanced, covering both simple and enterprise-grade agents. Every example should be runnable, minimal for its level, and build on the previous level.

Status: Levels 0-5 and 7 are built (each with a README and mocked tests); Level 6 is built except 6D (evals/replay) and 6E (hosted harnesses). Update the Commands and Layout sections below as the code is added.

## Stack and defaults

- **Language:** Python 3.10+ (primary). TypeScript variants are optional and go in a parallel `ts/` tree if added.
- **SDK:** the official `anthropic` package. Do not use raw `requests`/`httpx` or OpenAI-compatible shims against the Claude API.
- **Model:** read from the `CLAUDE_MODEL` env var, defaulting to `claude-opus-5-5`. Use exact model ID strings, never date-suffixed variants. Use cheaper models (`claude-sonnet-5-5`, `claude-haiku-5-5`) only where an example explicitly demonstrates model routing.
- **Thinking:** use `thinking={"type": "adaptive"}` for non-trivial tasks. Never use `budget_tokens` on current models (it returns a 400). Control depth with `output_config={"effort": ...}`.
- **Streaming:** stream anything with long input/output or large `max_tokens`; use `.get_final_message()` when per-event handling isn't needed.
- **No assistant prefill** (400 on current models). Use structured outputs (`output_config.format`) or system-prompt instructions.
- **Tool use:** forced `tool_choice` (`any`/`tool`) is rejected on the newest models. Use `auto` plus an explicit instruction, and `strict: true` on tools.
- **Refusals:** always check `stop_reason` (including `"refusal"`) before reading `content`.
- API shapes change often. Before writing SDK code, check the `claude-api` skill or the live docs rather than relying on memory.

## Curriculum / layout

**Source of truth:** the agenda and folder structure are defined in `/Users/davidbong/Documents/Claude_sdk_project/agenda.md`. Read it before creating or moving any folder or example. If it conflicts with the table below, `agenda.md` wins; update this section to match.

Each level is a self-contained folder with its own `README.md` (concept, how to run, what to try next). Higher levels may import shared helpers from `common/` but should not import from sibling levels.

| Level | Folder | Topics |
|---|---|---|
| 0 Setup | `00_setup/` | Env, API key, hello world, usage and cost |
| 1 Beginner | `01_llm_loop/` | First call, system prompts, the chat loop, streaming, thinking, structured outputs, errors |
| 2 Foundations | `02_tools/` | Tool definitions, manual tool loop, parallel calls, tool runner, server tools, documents |
| 3 Intermediate | `03_agents/` | Bounded agent loop, memory, prompt caching, token counting, context editing/compaction, planning |
| 4 MCP | `04_mcp/` | Build an MCP server, MCP client loop, MCP connector, remote auth, tool search, security |
| 5 Advanced | `05_workflows/` | Chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, subagents, model routing, batches |
| 6 Harness engineering | `06_harness/` | Context engineering, tool surface, sandbox, permissions, hooks, budgets, checkpointing, fallbacks, tracing, evals, Managed Agents |
| 7 Capstone | `07_enterprise_capstone/` | Production-style agent: MCP tools, approvals, tracing, evals, deployment |

`common/` holds shared config, logging, and tool helpers. `evals/` holds eval sets. `tests/` mirrors the level folders.

## Engineering rules

- **Start simple.** Prefer a single call, then a workflow, and use an agent only when the task needs open-ended, model-driven tool use. Say so in each example's README.
- **Secrets:** read `ANTHROPIC_API_KEY` from the environment or `.env` (git-ignored). Provide `.env.example`. The SDK also works with `ant auth login` profiles, so don't hard-fail when the env var is unset without checking. Never commit keys or log them.
- **Use SDK types and helpers** (`anthropic.types`, typed exceptions such as `RateLimitError`, stream helpers) instead of redefining them. Catch errors most-specific-first and retry only retryable ones (429, 5xx, connection).
- **Tool results:** return all parallel `tool_result` blocks in a single user message, and use `is_error: true` for failures. Parse tool inputs with `json.loads`, never string-match.
- **Agent loops must be bounded:** set max iterations, a token or cost budget, and timeouts. Log each turn's `usage` (including cache read/write tokens).
- **Enterprise-level examples** must show: input/output validation, least-privilege tools, approval gates for destructive actions, structured logs with request IDs, and a test or eval.
- **Don't truncate inputs silently.** If content exceeds the context window, chunk or summarize explicitly.
- Keep examples short and commented for the "why", not the "what". Match the existing style in neighboring files.

## Commands

Update these once the scaffolding exists.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # anthropic, python-dotenv, pytest
cp .env.example .env                 # then add ANTHROPIC_API_KEY
python 01_llm_loop/hello.py            # run an example
pytest                               # tests (mock the API; real-API tests are marked `live`)
```

Real API calls cost money. Mark tests that hit the API with `@pytest.mark.live` and skip them by default.

## Working with Claude Code in this repo

- Adding an example: create it in the right level folder, add a short README entry, and add a test (mocked) or an eval.
- Before changing model IDs, thinking, or tool config, consult the `claude-api` skill.
- Ask before running anything that makes many paid API calls (evals, batches, long agent runs).
