# Agenda: From a Simple LLM Loop to Advanced Harness Engineering

Source of truth for the curriculum and folder structure (referenced by `CLAUDE.md`).

**Stack:** Python 3.10+, official `anthropic` SDK. **Default model:** `claude-opus-5-5` (override with `CLAUDE_MODEL`).

**Progression:** single call, then a loop, then tools, then agents, then MCP, then workflows, then harness engineering, then an enterprise capstone.

**Rule for every module:** a runnable example, a short README (concept, run it, what to try next), and a mocked test or an eval. Each module ends with a checkpoint question you should be able to answer before moving on.

---

## Folder structure

```
Claude_sdk_project/
├── CLAUDE.md
├── agenda.md
├── README.MD
├── .env.example
├── requirements.txt
├── common/                  # config, logging, usage tracking, tool helpers
├── 00_setup/
├── 01_llm_loop/
├── 02_tools/
├── 03_agents/
├── 04_mcp/
├── 05_workflows/
├── 06_harness/
├── 07_enterprise_capstone/
├── evals/
└── tests/                   # mirrors the numbered folders
```

---

## Level 0: Setup (`00_setup/`)

- Python env, `anthropic` install, `.env` and `ANTHROPIC_API_KEY` (or `ant auth login` profile).
- Hello-world call; reading `response.usage`; choosing a model and where pricing lives.
- Repo conventions: `common/` helpers, mocked vs `live` tests.
- **Checkpoint:** What does a Messages API request and response look like, and what does it cost?

## Level 1: The simple LLM loop (`01_llm_loop/`) *Beginner*

| # | Topic | Output |
|---|---|---|
| 1.1 | First message: `messages.create`, `max_tokens`, `stop_reason` | `hello.py` |
| 1.2 | System prompts and role/prompt design | `system_prompt.py` |
| 1.3 | **The loop:** multi-turn chat REPL that keeps history | `chat_loop.py` |
| 1.4 | Streaming responses (`.stream()`, `.get_final_message()`) | `stream_chat.py` |
| 1.5 | Adaptive thinking and `effort`; thinking display | `thinking.py` |
| 1.6 | Structured outputs (`output_config.format`, `messages.parse`) | `extract_json.py` |
| 1.7 | Error handling: typed exceptions, retries, timeouts, refusals | `errors.py` |

- **Checkpoint:** Why is a chatbot "just a loop over a growing messages list", and where does it break (context size, cost)?

## Level 2: Tool use (`02_tools/`) *Foundations*

| # | Topic | Output |
|---|---|---|
| 2.1 | Defining tools (JSON schema, `strict: true`) | `define_tool.py` |
| 2.2 | **Manual tool loop:** `stop_reason == "tool_use"`, run tool, return `tool_result` | `manual_loop.py` |
| 2.3 | Parallel tool calls and `is_error` results | `parallel_tools.py` |
| 2.4 | Tool Runner (`@beta_tool`, `tool_runner`) vs manual loop | `tool_runner.py` |
| 2.5 | Tool design: naming, descriptions, error messages that help the model recover | `tool_design.md` |
| 2.6 | Server tools: web search, web fetch, code execution | `server_tools.py` |
| 2.7 | Files and documents input, PDFs, citations | `documents.py` |

- **Checkpoint:** What is the difference between a client tool and a server tool? Who runs the loop in each case?

## Level 3: Agents (`03_agents/`) *Intermediate*

| # | Topic | Output |
|---|---|---|
| 3.1 | When to build an agent vs a workflow (the four-criteria check) | `agent_or_not.md` |
| 3.2 | **A bounded agent loop:** max turns, token/cost budget, timeout, stop conditions | `agent.py` |
| 3.3 | A useful first agent (e.g. file/research assistant) with 3-5 tools | `research_agent.py` |
| 3.4 | State and memory: scratchpad, memory tool, persisting a session | `memory_agent.py` |
| 3.5 | Prompt caching: placement, verifying `cache_read_input_tokens` | `caching.py` |
| 3.6 | Token counting (`count_tokens`) and context-window budgeting | `count_tokens.py` |
| 3.7 | Long conversations: context editing vs compaction | `long_context.py` |
| 3.8 | Planning and self-verification (todo list, run-tests-then-fix) | `planner.py` |
| 3.9 | Choosing between the four agent approaches: manual loop, Tool Runner, Managed Agents, Claude Agent SDK | `choose_approach.md` |

- **Checkpoint:** How do you guarantee your agent loop terminates and stays within budget?

## Level 4: MCP, the Model Context Protocol (`04_mcp/`) *Intermediate to Advanced*

| # | Topic | Output |
|---|---|---|
| 4.1 | What MCP is: hosts, clients, servers; tools vs resources vs prompts | `mcp_overview.md` |
| 4.2 | **Build an MCP server** (Python, FastMCP): expose 2-3 tools, run over stdio | `server_basic/` |
| 4.3 | **Connect an MCP client to your own agent loop** (list tools, translate to API tools, call, return results) | `client_loop.py` |
| 4.4 | MCP connector in the Messages API (`mcp_servers` + `mcp_toolset`, beta header) for remote servers | `mcp_connector.py` |
| 4.5 | Remote MCP over HTTP: transport, auth (OAuth/bearer), secrets handling | `server_http/` |
| 4.6 | Resources and prompts; pagination; progress and errors | `server_resources/` |
| 4.7 | Tool search / `defer_loading` when you have many MCP tools | `tool_search.py` |
| 4.8 | MCP security: untrusted tool output, prompt injection, allowlists, least privilege | `mcp_security.md` |
| 4.9 | Testing MCP servers (MCP Inspector, unit tests, contract tests) | `tests/` |

- **Checkpoint:** When should a capability be an MCP server instead of a local function tool?

## Level 5: Workflow patterns (`05_workflows/`) *Advanced*

Each pattern is implemented without a framework, with a note on when *not* to use it.

| # | Pattern | Output |
|---|---|---|
| 5.1 | Prompt chaining (with gates between steps) | `chain.py` |
| 5.2 | Routing (classify, then dispatch to a specialized prompt/model) | `router.py` |
| 5.3 | Parallelization: sectioning and voting | `parallel.py` |
| 5.4 | Orchestrator-workers (dynamic task decomposition) | `orchestrator.py` |
| 5.5 | Evaluator-optimizer (generate, critique, refine) | `eval_opt.py` |
| 5.6 | Multi-agent / subagents with isolated contexts and a clean handoff contract | `subagents.py` |
| 5.7 | Model routing: Opus/Sonnet/Haiku by task; advisor tool pairing | `model_routing.py` |
| 5.8 | Batch processing (Message Batches API) for offline workloads | `batch_job.py` |

- **Checkpoint:** Which of these patterns would you use for your own problem, and what simpler design did you rule out?

## Level 6: Advanced harness engineering (`06_harness/`) *Advanced*

The harness is everything around the model: loop, tools, context, permissions, state, and observability. This level treats it as a product.

### 6A. Context engineering
| # | Topic | Output |
|---|---|---|
| 6.1 | Context budget design: what goes in the prompt, tools, history, and retrieved data | `context_budget.py` |
| 6.2 | Compaction and context editing strategies; what to preserve vs drop | `compaction.py` |
| 6.3 | Append-only history and **preserved thinking** rules: don't edit earlier turns; return thinking blocks unchanged | `append_only.py` |
| 6.4 | Cache-friendly prompt architecture: stable prefix, volatile suffix, mid-conversation system messages | `cache_architecture.py` |
| 6.5 | Just-in-time retrieval vs up-front loading; progressive disclosure (skills-style) | `jit_context.py` |

### 6B. Tool and action surface
| # | Topic | Output |
|---|---|---|
| 6.6 | Tool surface design: few general tools vs many narrow ones; bash and text-editor tools | `tool_surface.md` |
| 6.7 | Programmatic tool calling and tool search to cut token cost | `programmatic_tools.py` |
| 6.8 | Sandboxing and execution isolation (containers, filesystem and network limits) | `sandbox/` |
| 6.9 | Permission model: allow/ask/deny policies, human-in-the-loop approval gates | `permissions.py` |
| 6.10 | Hooks: pre/post tool interception, result modification, audit hooks | `hooks.py` |

### 6C. Control, reliability, and recovery
| # | Topic | Output |
|---|---|---|
| 6.11 | Task budgets, effort tuning per task, and cost ceilings | `budgets.py` |
| 6.12 | Checkpointing, resumable sessions, idempotent tool calls | `checkpoint.py` |
| 6.13 | Refusal handling and server-side fallbacks | `fallbacks.py` |
| 6.14 | Failure taxonomy: stuck loops, tool misuse, hallucinated success; loop and no-progress detection | `failure_modes.py` |
| 6.15 | Long-horizon runs: progress files, verification steps, clean-state handoff between sessions | `long_horizon.py` |
| 6.16 | Prompt-injection defense for agents (trust boundaries, output filtering) | `injection_defense.py` |

### 6D. Measurement
| # | Topic | Output |
|---|---|---|
| 6.17 | Observability: structured traces per turn (tokens, cache, latency, tool calls, cost) | `tracing.py` |
| 6.18 | Building an eval set; grading methods (code, LLM-judge, human) | `evals/` |
| 6.19 | Hill-climbing the harness against evals with a train/validation/test split | `hillclimb.md` |
| 6.20 | Regression testing: replaying recorded transcripts | `replay.py` |

### 6E. Hosted and packaged harnesses
| # | Topic | Output |
|---|---|---|
| 6.21 | Managed Agents: agents, environments, sessions, events, vaults, outcomes | `managed_agents/` |
| 6.22 | Claude Agent SDK as a batteries-included harness (compare with the one you built) | `agent_sdk_compare.md` |
| 6.23 | Scheduled and long-running deployments | `scheduled.md` |

- **Checkpoint:** Given a failing agent run, can you tell whether the fault is in the prompt, the tools, the context, or the harness, and prove it from traces?

## Level 7: Enterprise capstone (`07_enterprise_capstone/`)

Build one production-style agent that combines the levels above. Suggested: an internal **support/ops agent** that reads tickets, calls tools via MCP, and proposes or performs actions behind approvals.

- Architecture doc and threat model (tools, data, trust boundaries).
- MCP-backed tools with least-privilege credentials.
- Bounded harness with approvals, budgets, checkpointing, and fallbacks.
- Tracing, audit log, and an eval suite with a release gate.
- Deployment options: your own infra, or Bedrock/Vertex/Foundry clients, or Managed Agents.
- Cost report (per completed task, not per request) and runbook.
- **Done when:** the eval suite passes its threshold, a red-team prompt-injection test fails safely, and a run can be resumed after a forced crash.

---

## Suggested pacing

| Phase | Levels | Focus |
|---|---|---|
| Week 1 | 0-1 | The loop, streaming, structured output |
| Week 2 | 2 | Tools and server tools |
| Week 3 | 3 | Bounded agents, memory, caching, context |
| Week 4 | 4 | MCP server, client, security |
| Week 5 | 5 | Workflow patterns, subagents, batches |
| Weeks 6-7 | 6 | Harness engineering and evals |
| Week 8 | 7 | Capstone |

## Cross-cutting threads (revisit at every level)

- **Cost:** log `usage` on every call; cache early; measure per completed task.
- **Safety:** least privilege, approvals for irreversible actions, treat tool output as untrusted.
- **Evals:** every module adds at least one test case to `evals/` or `tests/`.
- **Simplicity:** prefer the simplest tier that works; document why a more complex design was needed.
