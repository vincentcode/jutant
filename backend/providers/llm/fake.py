"""FakeModel: scripted replies for tests."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from core.types import Message, ModelReply, ToolSpec


@dataclass(frozen=True)
class ModelCall:
    messages: list[Message]
    tools: list[ToolSpec]


class FakeModel:
    """Returns `replies` in order and records the messages and tools it was given."""

    def __init__(self, replies: list[ModelReply] | None = None, embedding_dim: int = 8):
        self.replies = list(replies or [])
        self.calls: list[ModelCall] = []
        self.embedding_dim = embedding_dim

    async def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply:
        self.calls.append(ModelCall(list(messages), list(tools)))
        if not self.replies:
            raise AssertionError("FakeModel ran out of scripted replies")
        return self.replies.pop(0)

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        reply = await self.chat(messages, [])
        for word in (reply.text or "").split(" "):
            yield word + " "

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7)] * self.embedding_dim for t in texts]
