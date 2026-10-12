"""1.7 Error handling: typed exceptions, SDK retries, timeouts, and refusals."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

import anthropic

from common.config import MODEL, make_client

# The SDK already retries 408/409/429/5xx and connection errors (default max_retries=2).
client = make_client().with_options(timeout=60.0, max_retries=3)


def ask(prompt: str) -> str | None:
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.BadRequestError as e:  # 400: fix the request, don't retry
        print(f"Bad request: {e.message}")
    except anthropic.AuthenticationError:
        print("Invalid API key")
    except anthropic.PermissionDeniedError:
        print("Key lacks permission")
    except anthropic.NotFoundError:
        print("Unknown model or endpoint")
    except anthropic.RateLimitError as e:  # still failing after SDK retries
        print(f"Rate limited; retry after {e.response.headers.get('retry-after', '60')}s")
    except anthropic.APIStatusError as e:  # catch-all for other HTTP errors; must come after the specific ones
        print(f"API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:  # also covers timeouts (APITimeoutError is a subclass)
        print("Network problem")
    else:
        # Always check stop_reason before trusting content.
        if response.stop_reason == "refusal":
            print("Refused:", response.stop_details)
        elif response.stop_reason == "max_tokens":
            print("Truncated: raise max_tokens")
        else:
            return next((b.text for b in response.content if b.type == "text"), None)
    return None


print(ask("Say hi."))
