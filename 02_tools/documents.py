"""2.7 Documents as input, with citations. Works with a PDF path or a built-in text sample.

Usage: python 02_tools/documents.py [path/to/file.pdf]
"""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from common.config import MODEL, log_usage, make_client

SAMPLE = (
    "Refund policy. Customers may request a refund within 30 days of purchase. "
    "Digital goods are refundable only if they have not been downloaded. "
    "Refunds are issued to the original payment method within 5 business days."
)
MAX_PDF_BYTES = 30 * 1024 * 1024  # request limit is 32 MB; fail loudly rather than truncate


def build_document(pdf_path: str | None) -> dict:
    if pdf_path:
        data = Path(pdf_path).read_bytes()
        if len(data) > MAX_PDF_BYTES:
            sys.exit("PDF too large for one request; split it or upload via the Files API.")
        source = {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.standard_b64encode(data).decode("ascii"),
        }
    else:
        source = {"type": "text", "media_type": "text/plain", "data": SAMPLE}
    # citations must be enabled on the document; it cannot be combined with output_config.format.
    return {"type": "document", "source": source, "title": "Source document", "citations": {"enabled": True}}


def main() -> None:
    client = make_client()
    pdf = sys.argv[1] if len(sys.argv) > 1 else None
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        output_config={"effort": "low"},
        messages=[{
            "role": "user",
            # Put the document before the question.
            "content": [build_document(pdf), {"type": "text", "text": "Can I get a refund on a downloaded ebook after 10 days?"}],
        }],
    )
    if response.stop_reason == "refusal":
        print("Refused:", response.stop_details)
        return

    for block in response.content:
        if block.type != "text":
            continue
        print(block.text, end="")
        # Cited text blocks carry a `citations` list pointing at the exact passage.
        for c in getattr(block, "citations", None) or []:
            where = (
                f"pages {c.start_page_number}-{c.end_page_number - 1}" if c.type == "page_location"
                else f"chars {c.start_char_index}-{c.end_char_index}"
            )
            print(f' [{where}: "{c.cited_text}"]', end="")
    print()
    log_usage(response)


if __name__ == "__main__":
    main()
