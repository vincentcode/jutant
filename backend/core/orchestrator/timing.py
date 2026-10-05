"""Where one turn's time goes: routing, the model, tools. Recorded with the answer in the audit
log, so a slow answer can be explained and a change can be measured."""

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from core.ports import ModelProvider
from core.types import Message, ModelReply, ToolSpec


@dataclass
class TurnTimer:
    started: float = field(default_factory=time.perf_counter)
    route_s: float = 0.0
    model_s: float = 0.0
    tool_s: float = 0.0
    embed_s: float = 0.0
    model_calls: int = 0

    def as_detail(self) -> dict[str, int]:
        def ms(seconds: float) -> int:
            return round(seconds * 1000)

        return {
            "total_ms": ms(time.perf_counter() - self.started),
            "route_ms": ms(self.route_s),
            "model_ms": ms(self.model_s),
            "tool_ms": ms(self.tool_s),
            "embed_ms": ms(self.embed_s),
            "model_calls": self.model_calls,
        }


class TimedModel:
    """A model provider that adds the time of each call to a TurnTimer."""

    def __init__(self, model: ModelProvider, timer: TurnTimer):
        self._model = model
        self._timer = timer

    async def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply:
        start = time.perf_counter()
        try:
            return await self._model.chat(messages, tools)
        finally:
            self._timer.model_s += time.perf_counter() - start
            self._timer.model_calls += 1

    async def stream_chat(
        self, messages: list[Message], tools: list[ToolSpec]
    ) -> AsyncIterator[str | ModelReply]:
        start = time.perf_counter()
        try:
            async for part in self._model.stream_chat(messages, tools):
                yield part
        finally:
            self._timer.model_s += time.perf_counter() - start
            self._timer.model_calls += 1

    async def embed(self, texts: list[str]) -> list[list[float]]:
        start = time.perf_counter()
        try:
            return await self._model.embed(texts)
        finally:
            self._timer.embed_s += time.perf_counter() - start

    def __getattr__(self, name: str) -> Any:  # the model's name and anything else it offers
        return getattr(self._model, name)
