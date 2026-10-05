"""Pulls named fields out of a document's text with one model call.

The model is asked for a JSON object with exactly the schema's fields. Its reply is parsed
defensively: a field it leaves out, leaves empty or cannot be parsed comes back as None, never
as a guess.
"""

import json
import re
from typing import Any

from core.ports import ModelProvider
from core.types import Message

PROMPT = (
    "Extract these fields from the document: {fields}.\n"
    "Reply with one JSON object with exactly these keys. Copy values as written in the document. "
    "Use null for any field the document does not contain. Do not guess."
)


async def extract(model: ModelProvider, text: str, fields: list[str]) -> dict[str, Any]:
    messages = [Message("system", PROMPT.format(fields=", ".join(fields))), Message("user", text)]
    reply = await model.chat(messages, [])
    parsed = parse_json_object(reply.text or "")
    return {name: _clean(parsed.get(name)) for name in fields}


def parse_json_object(text: str) -> dict[str, Any]:
    """The first JSON object in `text`, tolerating code fences and surrounding words."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        if value.lower() in {"", "null", "none", "n/a", "unknown"}:
            return None
    return value
