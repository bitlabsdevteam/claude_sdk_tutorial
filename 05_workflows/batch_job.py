"""5.8 Batch processing: submit many independent requests, come back later, pay ~50% less.

Use when: the work is offline and independent (classification, extraction, evals) and can wait up to 24h.
Don't use when: a user is waiting, or each request depends on the previous result.

Usage: python 05_workflows/batch_job.py              # submit, then wait up to 10 minutes
       python 05_workflows/batch_job.py <batch_id>   # resume: collect results of an earlier batch
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from common.config import make_client

BATCH_MODEL = "claude-haiku-5-5"  # simple labelling job: cheapest model, and the batch discount on top
REVIEWS = {
    "r1": "Love it, works perfectly!",
    "r2": "Arrived broken and support ignored me.",
    "r3": "It's okay, nothing special.",
    "r4": "Best purchase this year.",
}


def build_requests(items: dict[str, str], model: str = BATCH_MODEL) -> list[Request]:
    return [
        Request(custom_id=cid, params=MessageCreateParamsNonStreaming(
            model=model, max_tokens=20,
            messages=[{"role": "user", "content": f"Label as positive, negative or neutral. One word.\n\n{text}"}],
        ))
        for cid, text in items.items()
    ]


def wait(client, batch_id: str, timeout_s: float = 600, poll_s: float = 15) -> bool:
    """Poll until the batch ends. Returns False at the deadline; the batch keeps running server-side."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            return True
        print(f"[{batch.processing_status}] still processing: {batch.request_counts.processing}")
        time.sleep(poll_s)
    return False


def collect(client, batch_id: str) -> dict[str, str]:
    """Results arrive in ANY order: always key by custom_id, never by position."""
    out = {}
    for r in client.messages.batches.results(batch_id):
        if r.result.type == "succeeded":
            out[r.custom_id] = next((b.text for b in r.result.message.content if b.type == "text"), "").strip()
        else:  # errored | canceled | expired: report it, so the caller can resubmit just these
            out[r.custom_id] = f"<{r.result.type}>"
    return out


def main() -> None:
    client = make_client()
    if len(sys.argv) > 1:
        batch_id = sys.argv[1]
    else:
        batch_id = client.messages.batches.create(requests=build_requests(REVIEWS)).id
        print(f"submitted {batch_id} ({len(REVIEWS)} requests)")
    if not wait(client, batch_id):
        sys.exit(f"Not finished yet. Resume later: python 05_workflows/batch_job.py {batch_id}")
    for cid, label in sorted(collect(client, batch_id).items()):
        print(f"{cid}: {label}  <- {REVIEWS.get(cid, '?')}")


if __name__ == "__main__":
    main()
