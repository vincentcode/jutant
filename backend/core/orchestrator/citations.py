"""Collects the sources (document sections, record references) cited by tool results,
so every answer can show where it came from."""

from collections.abc import Iterable

from core.types import Citation, ToolResult


def collect(results: Iterable[ToolResult]) -> tuple[Citation, ...]:
    """Every citation from successful results, de-duplicated, in first-seen order."""
    seen: dict[Citation, None] = {}
    for result in results:
        if result.ok:
            for citation in result.citations:
                seen.setdefault(citation, None)
    return tuple(seen)
