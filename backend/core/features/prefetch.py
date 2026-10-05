"""Tool calls made in code before the model is asked.

A feature can name calls whose arguments come straight from the question: the whole question
as a search query, or a value matched by a pattern (a transfer reference, a customer number).
When every argument of a call can be filled, the call is made at once, through the gateway like
any other, and the model starts with its result. That saves the model step that would only
have chosen the call, about 30 seconds on a CPU.
"""

import re
from typing import Any
from uuid import uuid4

from core.types import ArgumentSource, Feature, ToolCall


def planned_calls(feature: Feature, question: str) -> list[ToolCall]:
    """The feature's prefetch calls whose every argument the question supplies."""
    calls = []
    for prefetch in feature.prefetch:
        arguments = {name: _value(source, question) for name, source in prefetch.arguments.items()}
        if all(value is not None for value in arguments.values()):
            calls.append(ToolCall(f"prefetch_{uuid4().hex[:8]}", prefetch.tool, arguments))
    return calls


def _value(source: ArgumentSource, question: str) -> Any:
    if source.question:
        return question
    if source.match is not None:
        found = re.search(source.match, question)
        if found is None:
            return None
        return found.group(1) if found.re.groups else found.group(0)
    return source.value
