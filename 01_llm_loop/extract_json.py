"""1.6 Structured outputs: get a validated object back instead of parsing text."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable

from pydantic import BaseModel

from common.config import MODEL, log_usage, make_client


# The Pydantic model is the contract: the API constrains output to this schema,
# and the SDK validates it, so no regex or json.loads on free text.
class ContactInfo(BaseModel):
    name: str
    email: str
    plan: str
    interests: list[str]


client = make_client()

response = client.messages.parse(
    model=MODEL,
    max_tokens=2048,
    messages=[{
        "role": "user",
        "content": "Extract: Jane Doe (jane@co.com) wants Enterprise, interested in API and SDKs.",
    }],
    output_format=ContactInfo,  # parse() sends this as output_config.format and validates the reply
)

contact = response.parsed_output  # a validated ContactInfo
print(contact)
log_usage(response)
