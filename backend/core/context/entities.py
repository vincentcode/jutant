"""Finding entities: in a message, in the arguments of the tools a turn called, and in the
sources its answer cited.

Not in answers' text: a narration such as "Transfer to 5566778899" would be read as an account.
An entity's id is what its type's pattern matches (its first group, or the whole match).

Names are learned from tool results, for types whose pack names a `name_field`: a record with
an id of that type and a name ("SAV-STD", "Standard Savings") teaches the conversation that the
name means the id, so "the Standard Savings rate" later points to SAV-STD without the model.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from core.types import Citation, EntityType, ToolCall

DOCUMENT = "document"  # a document an answer cited, by title: what a follow-up searches with


def entities_in(
    text: str, types: Sequence[EntityType], names: Mapping[str, tuple[str, str]] | None = None
) -> dict[str, str]:
    """Each type's first id in `text`: by its pattern, or else by a name learned earlier
    (`names`: lower-case name -> (type, id))."""
    found: dict[str, str] = {}
    for entity_type in types:
        match = re.search(entity_type.pattern, text)
        if match is not None:
            found[entity_type.name] = match.group(1) if match.re.groups else match.group(0)
    for name, (kind, value) in (names or {}).items():
        if kind not in found and re.search(rf"(?i)\b{re.escape(name)}\b", text):
            found[kind] = value
    return found


def values_in(data: Any, types: Sequence[EntityType]) -> dict[str, str]:
    """Entities a record points to: its values that are exactly an id of a type
    (`failure_code: "E51"`), in a single record and the records inside it. Only exact values:
    a narration such as "Transfer to 5566778899" is not an account. Lists of records are
    skipped: which of their ids is meant is not known."""
    if not isinstance(data, dict):
        return {}
    found: dict[str, str] = {}
    for record in _records(data):
        for value in record.values():
            if not isinstance(value, str):
                continue
            for entity_type in types:
                if entity_type.name in found:
                    continue
                match = re.fullmatch(entity_type.pattern, value.strip())
                if match is not None:
                    found[entity_type.name] = match.group(1) if match.re.groups else match.group(0)
    return found


def names_in(data: Any, types: Sequence[EntityType]) -> dict[str, tuple[str, str]]:
    """Names a tool result teaches: lower-case name -> (type, id), from each record that has an
    id of a named type and that type's name field."""
    named = [t for t in types if t.name_field]
    learned: dict[str, tuple[str, str]] = {}
    for record in _records(data):
        for entity_type in named:
            name = record.get(entity_type.name_field or "")
            if not isinstance(name, str) or not name.strip():
                continue
            for key, value in record.items():
                if key == entity_type.name_field or not isinstance(value, str):
                    continue
                match = re.fullmatch(entity_type.pattern, value.strip())
                if match is not None:
                    found = match.group(1) if match.re.groups else match.group(0)
                    learned[name.strip().lower()] = (entity_type.name, found)
                    break
    return learned


def _records(data: Any) -> list[dict[str, Any]]:
    """The result's records: itself if a mapping, or the mappings in it (one level down)."""
    if isinstance(data, dict):
        return [data, *[v for v in data.values() if isinstance(v, dict)]]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def from_calls(
    calls: Iterable[ToolCall], citations: Iterable[Citation], types: Sequence[EntityType]
) -> dict[str, str]:
    """The entities a turn looked at: in its tool calls' arguments, then in its record sources
    (a later one replaces an earlier one of the same type), and the last document it cited."""
    found: dict[str, str] = {}
    for call in calls:
        for value in call.arguments.values():
            if isinstance(value, str):
                found.update(entities_in(value, types))
    for citation in citations:
        if citation.kind == "record":
            found.update(entities_in(citation.locator, types))
        elif citation.kind == "document":
            found[DOCUMENT] = citation.title
    return found
