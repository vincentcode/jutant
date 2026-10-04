"""PII masking before write: account numbers, phone numbers, ID numbers and emails.

Patterns are configurable per pack.
"""

from typing import Any


def mask(detail: dict[str, Any], patterns: dict[str, str] | None = None) -> dict[str, Any]:
    raise NotImplementedError
