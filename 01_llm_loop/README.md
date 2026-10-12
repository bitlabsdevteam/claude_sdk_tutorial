# Level 1: The simple LLM loop

Run from the project root with the venv active (`source .venv/bin/activate`).

| Script | Concept | Run |
|---|---|---|
| `hello.py` | One request; `stop_reason`; `usage` | `python 01_llm_loop/hello.py` |
| `system_prompt.py` | System prompts change behavior | `python 01_llm_loop/system_prompt.py` |
| `chat_loop.py` | **The loop**: stateless API, you resend history | `python 01_llm_loop/chat_loop.py` |
| `stream_chat.py` | Streaming + `get_final_message()` | `python 01_llm_loop/stream_chat.py` |
| `thinking.py` | Adaptive thinking, `effort`, summarized display | `python 01_llm_loop/thinking.py` |
| `extract_json.py` | Structured outputs with a Pydantic model | `python 01_llm_loop/extract_json.py` |
| `errors.py` | Typed exceptions, timeouts, refusals | `python 01_llm_loop/errors.py` |

Shared helpers (`MODEL`, `make_client`, `log_usage`) live in `common/config.py`. Every call costs money, so `chat_loop.py` caps the number of turns.

## Things to try

- In `chat_loop.py`, print `len(messages)` and watch input tokens grow each turn.
- In `thinking.py`, compare `output_tokens` at `low` vs `high` effort.
- In `errors.py`, set a bad `CLAUDE_MODEL` and see which branch fires.

## Checkpoint

Why is a chatbot "just a loop over a growing messages list", and where does it break (context size, cost)?

## Next

Level 2: `02_tools/`.
