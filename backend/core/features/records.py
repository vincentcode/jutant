"""Record answers assembled in code: what one record states, and what it does not.

A small model given a record and a reference document together mixes them: asked "was it
reversed?" about a failed transfer whose record says nothing of a reversal, it states the
document's general rule ("funds return within two working days") as what happened. So when a
lookup fetched exactly one record:

- its fields are set out in code as the facts about it, and documents are named as general
  rules, never to be stated as something that happened to it;
- the model picks which field the question is about (one id from a short list, which a small
  model does reliably), or "overview" for the record as a whole, or "none";
- for "none" the answer is written in code: the record does not show that. The model never
  gets the chance to fill the gap.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.features.matching import Option, ask_model
from core.ports import ModelProvider
from core.types import ToolResult

OVERVIEW = "overview"
NONE = "none"
WHICH = (
    "A staff member asks about the record {name}. Which of its fields says what they ask? "
    "Choose overview if they ask what happened or about the record as a whole, and none if no "
    "field says it."
)
FACTS = (
    "The facts the record {name} states:\n{fields}\n"
    "Only these are facts about {name}. A document gives general rules: never state one as "
    "something that happened to {name}. If the record does not state what was asked, say "
    '"The record does not show" that.'
)
FOCUS = "The question is about its {field}."
NOT_SHOWN = "The record for {name} does not show that."
SEE = " For what generally applies, see {sources}."


@dataclass(frozen=True)
class Record:
    kind: str  # "Transaction"
    reference: str  # "TX-0002"
    fields: dict[str, str]

    @property
    def name(self) -> str:
        return f"{self.kind.lower()} {self.reference}"


def single_record(results: Sequence[ToolResult]) -> Record | None:
    """The one record the turn fetched, if exactly one: a result citing a record, holding one
    object with fields (not a list of them, nor an empty one: nothing to set out)."""
    found = [
        Record(citation.title, citation.locator, _fields(result.data))
        for result in results
        if result.ok and isinstance(result.data, Mapping) and result.data
        for citation in result.citations[:1]
        if citation.kind == "record"
    ]
    return found[0] if len(found) == 1 else None


def document_sources(results: Sequence[ToolResult]) -> list[str]:
    """The documents the turn found, as "title, section", once each."""
    sources = [
        f"{c.title}, {c.locator}"
        for r in results
        if r.ok
        for c in r.citations
        if c.kind == "document"
    ]
    return list(dict.fromkeys(sources))


async def field_asked(model: ModelProvider, question: str, record: Record) -> str | None:
    """The field the question is about, OVERVIEW, NONE, or None if the model cannot tell."""
    options = [Option(name, f"{_label(name)}: {value}") for name, value in record.fields.items()]
    options += [
        Option(OVERVIEW, "what happened, or the record as a whole"),
        Option(NONE, "no field says what they ask"),
    ]
    return await ask_model(model, WHICH.format(name=record.name), question, options)


def facts(record: Record, field: str | None) -> str:
    """The record's facts for the model, with the field the question is about, if one."""
    lines = "\n".join(f"- {_label(name)}: {value}" for name, value in record.fields.items())
    text = FACTS.format(name=record.name, fields=lines)
    if field in record.fields:
        text += " " + FOCUS.format(field=_label(field))
    return text


def not_shown(record: Record, sources: Sequence[str]) -> str:
    """The answer when no field of the record says what was asked."""
    text = NOT_SHOWN.format(name=record.name)
    return text + SEE.format(sources="; ".join(sources)) if sources else text


def _fields(data: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    """Field name -> value as text; nested objects flattened ("limits.daily"), lists joined."""
    fields: dict[str, str] = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            fields.update(_fields(value, f"{name}."))
        elif isinstance(value, list | tuple):
            fields[name] = ", ".join(str(v) for v in value) or "none"
        else:
            fields[name] = "none" if value is None else str(value)
    return fields


def _label(name: str) -> str:
    return name.replace("_", " ").replace(".", " ")
