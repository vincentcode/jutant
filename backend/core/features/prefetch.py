"""Tool calls made in code before the model is asked.

A feature can name calls whose arguments come straight from the question or the conversation:
the whole question as a search query, a value matched by a pattern, or the subject's current
entity of a type (the transfer staff are talking about, named now or earlier). Or the model
chooses an argument from the values the pack lists (`choose`: a request type): picking one id
from a short list is what a small model does reliably, where writing the call itself is not
(it calls a search it already has results from instead, or makes up the value). Or a detail
staff gave (`core.features.needs`): the system to look in, a phone number, a date. An `optional`
argument with no value is left out of the call, rather than the call not being made.
When every argument of a call can be filled, the call is made at once, through the gateway like
any other, and the model starts with its result. That saves the model step that would only
have chosen the call, about 30 seconds on a CPU.
"""

import re
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from core.features.matching import Option, ask_model
from core.ports import ModelProvider
from core.types import ArgumentSource, Feature, ToolCall

CHOOSE = "Which of these is the staff member's question about? Choose none if none fits."
NONE = "none"


def planned_calls(
    feature: Feature,
    question: str,
    entities: Mapping[str, str] | None = None,
    details: Mapping[str, str] | None = None,
) -> list[ToolCall]:
    """The feature's prefetch calls whose every argument the question, the subject's
    `entities` (type -> id) or its `details` (name -> value) supply."""
    calls = []
    for prefetch in feature.prefetch:
        if any(source.choose for source in prefetch.arguments.values()):
            continue  # the model chooses one of its arguments: `chosen_calls`
        arguments = {
            name: _value(source, question, entities or {}, details or {})
            for name, source in prefetch.arguments.items()
        }
        if all(v is not None or prefetch.arguments[n].optional for n, v in arguments.items()):
            arguments = {n: v for n, v in arguments.items() if v is not None}
            calls.append(ToolCall(f"prefetch_{uuid4().hex[:8]}", prefetch.tool, arguments))
    return calls


async def chosen_calls(
    model: ModelProvider,
    feature: Feature,
    question: str,
    entities: Mapping[str, str] | None = None,
) -> list[ToolCall]:
    """The feature's prefetch calls with an argument the model chooses from the pack's values,
    each made when the model picks one (not none) and every other argument is supplied."""
    calls = []
    for prefetch in feature.prefetch:
        if not any(source.choose for source in prefetch.arguments.values()):
            continue
        arguments: dict[str, Any] = {}
        for name, source in prefetch.arguments.items():
            if source.choose:
                options = [Option(v, meaning) for v, meaning in source.choose]
                picked = await ask_model(
                    model, CHOOSE, question, [*options, Option(NONE, "none of these")]
                )
                value = None if picked in (None, NONE) else picked
            else:
                value = _value(source, question, entities or {}, {})
            if value is None and source.optional:
                continue
            if value is None:
                break
            arguments[name] = value
        else:
            calls.append(ToolCall(f"prefetch_{uuid4().hex[:8]}", prefetch.tool, arguments))
    return calls


def _value(
    source: ArgumentSource,
    question: str,
    entities: Mapping[str, str],
    details: Mapping[str, str],
) -> Any:
    if source.question:
        return question
    if source.entity is not None:
        return entities.get(source.entity)
    if source.detail is not None:
        return details.get(source.detail)
    if source.match is not None:
        found = re.search(source.match, question)
        if found is None:
            return None
        return found.group(1) if found.re.groups else found.group(0)
    return source.value
