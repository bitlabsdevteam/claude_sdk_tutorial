"""Context helpers shared by Level 6: a cheap offline token estimate and message inspection."""
import json


def plain(obj):
    """SDK block objects -> JSON-friendly data (dicts pass through)."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)
    raise TypeError(f"not serializable: {type(obj)}")


def approx_tokens(obj) -> int:
    """Rough estimate (~4 chars per token) so budgeting works offline. For exact numbers use count_tokens (3.6)."""
    text = obj if isinstance(obj, str) else json.dumps(obj, default=plain)
    return max(1, len(text) // 4) if text else 0


def block_type(block) -> str | None:
    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)


def blocks_of(message: dict) -> list:
    """A message's content as a list of blocks (a plain string counts as one text block)."""
    content = message["content"]
    return [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
