"""OllamaProvider: chat, tools and embeddings against Ollama.

Uses `/api/chat` and `/api/embed`. Sets `num_ctx` explicitly. If the model returns a tool call as
JSON text in the content, it is parsed as a tool call.
"""

from collections.abc import AsyncIterator

from core.types import Message, ModelReply, ToolSpec


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        embed_model: str,
        num_ctx: int = 8192,
        temperature: float = 0.1,
        timeout_s: int = 300,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.timeout_s = timeout_s

    async def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply:
        raise NotImplementedError

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
