"""A model provider whose every call is recorded as a span of the trace it was given."""

from collections.abc import AsyncIterator
from typing import Any

from core.observability.tracer import Trace
from core.ports import ModelProvider
from core.types import Message, ModelReply, ToolSpec


class TracedModel:
    def __init__(self, model: ModelProvider, trace: Trace):
        self._model = model
        self._trace = trace

    async def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply:
        with self._trace.span("model", "llm", **self._request(messages, tools)) as span:
            reply = await self._model.chat(messages, tools)
            span.set(**_reply(reply, span))
            return reply

    async def stream_chat(
        self, messages: list[Message], tools: list[ToolSpec]
    ) -> AsyncIterator[str | ModelReply]:
        with self._trace.span(
            "model", "llm", streamed=True, **self._request(messages, tools)
        ) as span:
            async for part in self._model.stream_chat(messages, tools):
                if isinstance(part, ModelReply):
                    span.set(**_reply(part, span))
                yield part

    async def embed(self, texts: list[str]) -> list[list[float]]:
        with self._trace.span(
            "embed", "embedding", texts=len(texts), input=self._trace.text(texts)
        ):
            return await self._model.embed(texts)

    def __getattr__(self, name: str) -> Any:  # the model's name and anything else it offers
        return getattr(self._model, name)

    def _request(self, messages: list[Message], tools: list[ToolSpec]) -> dict[str, Any]:
        return {
            "model": getattr(self._model, "model", None),
            "tools": ", ".join(t.name for t in tools) or None,
            "messages": self._trace.text(
                [{"role": m.role, "content": m.content} for m in messages]
            ),
        }


def _reply(reply: ModelReply, trace: Trace) -> dict[str, Any]:
    calls = [{"name": c.name, "arguments": trace.masked(c.arguments)} for c in reply.tool_calls]
    return {
        "reply": trace.text(reply.text) if reply.text else None,
        "reply.tool_calls": calls or None,
        "tokens.prompt": reply.prompt_tokens,
        "tokens.completion": reply.completion_tokens,
    }
