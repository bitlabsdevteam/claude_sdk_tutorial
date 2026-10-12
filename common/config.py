"""Shared config: loads .env, exposes MODEL and a ready client."""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # runs once on import, so every level that imports `common` gets the same settings

# Exact model ID, never date-suffixed. CLAUDE_MODEL lets an example switch models without code changes.
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")


def make_client() -> Anthropic:
    # Reads ANTHROPIC_API_KEY (or an `ant auth login` profile) automatically,
    # so we never hard-fail or handle the key ourselves.
    return Anthropic()


def log_usage(response) -> None:
    # One line per call keeps cost visible. Levels 3+ also log cache tokens (see 03_agents/agent.py).
    u = response.usage
    print(f"[usage] in={u.input_tokens} out={u.output_tokens} stop={response.stop_reason}")
