"""Schema-driven field extraction.

One model call per document; JSON output validated; missing fields are `None`, never guessed.
"""

from typing import Any

from core.ports import ModelProvider


async def extract(model: ModelProvider, text: str, fields: list[str]) -> dict[str, Any]:
    raise NotImplementedError
