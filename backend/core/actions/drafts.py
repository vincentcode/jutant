"""Reading what a propose tool returned, and what a perform tool did. Pure functions.

A propose tool answers `{"summary", "fields": [{"label", "value"}], "submit": {...}, "notes",
"warnings"}` when the request can be made, or anything without `submit` (`{"refused": "You have
3 days left"}`) when it cannot: that goes back to the model to explain, and no card is shown.
A perform tool answers `{"reference": "LV-2026-00318", "status": "Waiting for your manager"}`.

Whatever a server sends is bounded here, so a card can never carry more than it can show.
"""

from typing import Any

from core.actions.types import Draft, Field

MAX_FIELDS = 12
MAX_LINES = 6  # notes, and warnings
MAX_TEXT = 300


def read_draft(data: Any) -> Draft | None:
    """The draft in a propose tool's result, or None if it proposes nothing."""
    if not isinstance(data, dict) or not isinstance(data.get("submit"), dict):
        return None
    fields = tuple(
        Field(_text(f.get("label")), _text(f.get("value")))
        for f in _list(data.get("fields"))[:MAX_FIELDS]
        if isinstance(f, dict) and f.get("label")
    )
    return Draft(
        summary=_text(data.get("summary")),
        fields=fields,
        submit=dict(data["submit"]),
        notes=_lines(data.get("notes")),
        warnings=_lines(data.get("warnings")),
    )


def read_outcome(data: Any) -> tuple[str, str]:
    """(reference, status) from a perform tool's result; empty where it gave none."""
    if not isinstance(data, dict):
        return "", ""
    return _text(data.get("reference")), _text(data.get("status"))


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _lines(value: Any) -> tuple[str, ...]:
    return tuple(_text(v) for v in _list(value)[:MAX_LINES] if v)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()[:MAX_TEXT]
