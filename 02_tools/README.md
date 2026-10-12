# Level 2: Tool use

Run from the project root with the venv active. Claude never runs your code: it returns a `tool_use` request, you run it and reply with a `tool_result`. Use a tool loop only when the model must act or fetch data; for one-shot answers a single call is simpler.

| Script | Concept | Run |
|---|---|---|
| `define_tool.py` | Tool schema, `strict: true`, `stop_reason == "tool_use"` | `python 02_tools/define_tool.py` |
| `manual_loop.py` | **The manual loop**, bounded by `MAX_TURNS` | `python 02_tools/manual_loop.py` |
| `parallel_tools.py` | Parallel calls, all results in one message, `is_error` | `python 02_tools/parallel_tools.py` |
| `tool_runner.py` | `@beta_tool` + `tool_runner` (SDK owns the loop; beta) | `python 02_tools/tool_runner.py` |
| `tool_design.md` | Naming, descriptions, helpful errors | read it |
| `server_tools.py` | Web search and code execution run by Anthropic | `python 02_tools/server_tools.py [search\|code]` |
| `documents.py` | PDF/text input with citations | `python 02_tools/documents.py [file.pdf]` |

Offline demo tools (`get_weather`, `calculate`) live in `common/demo_tools.py`. Tests: `pytest tests/02_tools` (mocked, no API calls). Server-tool and document demos cost more tokens; run them deliberately.

## Manual loop vs Tool Runner

Prefer the Tool Runner for plain custom-tool agents. Use the manual loop when you want to own every step (or avoid a beta dependency). Approval gates fit in either.

## Things to try

- In `manual_loop.py`, print `messages` after each turn and match each `tool_use_id` to its `tool_result`.
- In `parallel_tools.py`, remove `is_error` and see how the answer about "Atlantis" changes.
- In `tool_runner.py`, set `max_iterations=1` and see what happens.
- Note: forced `tool_choice` (`any`/`tool`) returns 400 on current models; use `auto` plus an instruction.

## Checkpoint

What is the difference between a client tool and a server tool? Who runs the loop in each case?

*Client tool:* you execute it and run the loop (manual, or the Tool Runner does it for you). *Server tool:* Anthropic executes it; you only handle `pause_turn` and read the result blocks.

## Next

Level 3: `03_agents/`.
