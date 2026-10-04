"""Core events -> server-sent events.

Each event becomes `event: <name>` and `data: <json>`. A comment line is sent every 15 seconds
as a keep-alive, because CPU generation can pause for long periods.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from core.events import Event

KEEPALIVE_S = 15
EVENT_NAMES = (
    "queued",
    "feature_selected",
    "tool_started",
    "tool_finished",
    "text_delta",
    "playbook_step",
    "completed",
    "failed",
)


def frame(name: str, data: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


def to_frame(event: Event) -> str:
    raise NotImplementedError


async def stream(events: AsyncIterator[Event]) -> AsyncIterator[str]:
    raise NotImplementedError
    yield  # pragma: no cover
