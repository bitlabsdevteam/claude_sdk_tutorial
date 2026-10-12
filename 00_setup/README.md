# Level 0: Setup

Goal: get a working environment and make your first Messages API call.

## Steps

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then set ANTHROPIC_API_KEY in .env
python 00_setup/hello.py
```

## What to look at

- `response.content[0].text`: the model's reply.
- `response.stop_reason`: why generation ended (`end_turn`, `max_tokens`, `tool_use`, `refusal`).
- `response.usage`: input/output tokens, which is what you pay for.

## Checkpoint

What does a Messages API request and response look like, and what does it cost?

## Next

Level 1: `01_llm_loop/`.
