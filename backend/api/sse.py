"""Turns the orchestrator's events into a server-sent event stream.

Each event becomes one `event: <name>` / `data: <json>` frame. A request that has to wait for a
free generation slot first receives `queued` with its place. A comment line is sent every 15
seconds while nothing else is, because CPU generation can pause for long periods and proxies
drop silent connections. If the client goes away, the generation is cancelled and its slot freed.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from dataclasses import asdict
from typing import Any

from api.queue import GenerationQueue
from core.errors import PolicyDenied
from core.events import (
    Completed,
    Event,
    Failed,
    FeatureSelected,
    PlaybookStepShown,
    TextDelta,
    ToolFinished,
    ToolStarted,
)

logger = logging.getLogger(__name__)

KEEPALIVE_S = 15.0
KEEPALIVE = ": keep-alive\n\n"


def frame(name: str, data: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


def to_frame(event: Event) -> str:
    match event:
        case FeatureSelected(feature_id):
            return frame("feature_selected", {"feature_id": feature_id})
        case ToolStarted(call):
            return frame("tool_started", {"call": asdict(call)})
        case ToolFinished(result):
            # The data itself stays on the server; the client shows that a tool ran and its sources.
            return frame(
                "tool_finished",
                {
                    "result": {
                        "call_id": result.call_id,
                        "ok": result.ok,
                        "error": result.error,
                        "citations": [asdict(c) for c in result.citations],
                    }
                },
            )
        case TextDelta(text):
            return frame("text_delta", {"text": text})
        case PlaybookStepShown(playbook_id, step):
            fields = ("order", "title", "instruction", "expects", "choices")
            return frame(
                "playbook_step",
                {"playbook_id": playbook_id, "step": {f: getattr(step, f) for f in fields}},
            )
        case Completed(answer):
            return frame(
                "completed",
                {
                    "answer": {
                        "text": answer.text,
                        "feature_id": answer.feature_id,
                        "citations": [asdict(c) for c in answer.citations],
                    }
                },
            )
        case Failed(reason):
            return frame("failed", {"reason": reason})
    raise TypeError(f"unknown event {event!r}")


async def stream(
    queue: GenerationQueue,
    make_events: Callable[[], AsyncIterator[Event]],
    keepalive_s: float = KEEPALIVE_S,
) -> AsyncIterator[str]:
    async def frames() -> AsyncIterator[str]:
        if queue.busy:
            yield frame("queued", {"position": queue.position()})
        async with queue.slot():
            try:
                async for event in make_events():
                    yield to_frame(event)
            except PolicyDenied:
                yield frame("failed", {"reason": "denied"})
            except Exception:
                logger.exception("generation failed")
                yield frame("failed", {"reason": "error"})

    async for chunk in with_keepalive(frames(), keepalive_s):
        yield chunk


async def with_keepalive(source: AsyncIterator[str], interval: float) -> AsyncIterator[str]:
    """Pass `source` through, adding a keep-alive comment whenever it is silent for `interval`."""
    items: asyncio.Queue[object] = asyncio.Queue()
    done = object()

    async def pump() -> None:
        try:
            async for item in source:
                await items.put(item)
        except Exception as exc:
            await items.put(exc)
        await items.put(done)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(items.get(), interval)
            except TimeoutError:
                yield KEEPALIVE
                continue
            if item is done:
                return
            if isinstance(item, Exception):
                raise item
            yield item  # type: ignore[misc]
    finally:
        task.cancel()  # the client went away, or the stream ended: stop generating
        with suppress(asyncio.CancelledError):
            await task
