"""Masks personal data in audit detail before it is written.

Emails, phone numbers and long digit runs (account, card and ID numbers) are masked wherever
they appear in string values, at any depth. The last four digits of a number are kept, so staff
reviewing the log can still tell records apart. A pack can replace or extend the patterns.
"""

import re
from collections.abc import Mapping
from typing import Any

DEFAULT_PATTERNS: dict[str, str] = {
    "email": r"[\w.+-]+@[\w-]+(\.[\w-]+)+",
    "phone": r"\+\d[\d\s-]{7,}\d",  # international form, e.g. +233 24 123 4567
    "card": r"\b(?:\d[ -]?){12,18}\d\b",  # 13-19 digits, grouped or not
    "id": r"\b[A-Z]{2,4}-\d{6,}(?:-\d+)?\b",  # e.g. GHA-123456789-0
    "number": r"\b\d{8,}\b",  # account numbers; dates like 2026-09-28 are left alone
}


def mask(detail: Any, patterns: Mapping[str, str] | None = None) -> Any:
    compiled = [re.compile(p) for p in (patterns or DEFAULT_PATTERNS).values()]
    return _mask(detail, compiled)


def _mask(value: Any, compiled: list[re.Pattern[str]]) -> Any:
    if isinstance(value, str):
        for pattern in compiled:
            value = pattern.sub(_redact, value)
        return value
    if isinstance(value, Mapping):
        return {k: _mask(v, compiled) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_mask(v, compiled) for v in value]
    return value


def _redact(match: re.Match[str]) -> str:
    text = match.group(0)
    if "@" in text:
        return "***@***"
    digits = re.sub(r"\D", "", text)
    return "*" * max(len(digits) - 4, 4) + digits[-4:]
