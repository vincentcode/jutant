"""OllamaProvider: chat, tool calls and embeddings against an Ollama server.

Uses `/api/chat` and `/api/embed`. The context size (`num_ctx`) is always set, because Ollama's
default is too small for a system prompt, history and tool results together.

Small models sometimes write a tool call as JSON in the reply text instead of using the tool
call field. When the text is exactly such a call to one of the offered tools, it is treated as
a tool call. Tool names are sent as written in the pack (`server.tool`): the prompts name them
that way, and Ollama drops a call whose name matches no offered tool, leaving an empty reply.
A call that comes back as `server__tool` is still mapped to its tool.
"""

import json
import re
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx

from core.errors import ModelUnavailable
from core.types import Message, ModelReply, ToolCall, ToolSpec

# Qwen wraps tool calls in <tool_call> tags when it writes them as text.
TOOL_CALL_TAGS = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
TOOL_CALL_OPEN = "<tool_call>"


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
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.model = model
        self.embed_model = embed_model
        self.num_ctx = num_ctx
        self.temperature = temperature
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        """Whether Ollama answers and has the chat model, for the health check."""
        try:
            response = await self._http.get("/api/tags")
            models = {m.get("name") for m in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            return False
        return self.model in models or f"{self.model}:latest" in models

    async def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply:
        data = await self._post("/api/chat", self._chat_body(messages, tools, stream=False))
        message = data.get("message") or {}
        return _reply(message.get("content") or "", message.get("tool_calls") or [], tools)

    async def stream_chat(
        self, messages: list[Message], tools: list[ToolSpec]
    ) -> AsyncIterator[str | ModelReply]:
        """Text is passed on as it arrives, except while it could still be a tool call written
        as text (it starts with `{` or `<tool_call>`): that is held until it is clearly not."""
        body = self._chat_body(messages, tools, stream=True)
        content, sent, wire_calls = "", 0, []
        holding = bool(tools)
        try:
            async with self._http.stream("POST", "/api/chat", json=body) as response:
                _raise_for_status(response)
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    message = chunk.get("message") or {}
                    wire_calls.extend(message.get("tool_calls") or ())
                    content += message.get("content") or ""
                    if holding:
                        holding = _may_be_text_call(content)
                    if not holding and not wire_calls:
                        sent = sent or len(content) - len(content.lstrip())  # no leading space
                        if len(content) > sent:
                            yield content[sent:]
                            sent = len(content)
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"Ollama stream failed: {exc}") from exc
        yield _reply(content, wire_calls, tools)

    def _chat_body(
        self, messages: list[Message], tools: list[ToolSpec], *, stream: bool
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [_to_wire(m) for m in messages],
            "stream": stream,
            "options": self._options(),
        }
        if tools:
            body["tools"] = [_tool_to_wire(t) for t in tools]
        return body

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        data = await self._post("/api/embed", {"model": self.embed_model, "input": texts})
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise ModelUnavailable("Ollama returned no embeddings")
        return embeddings

    def _options(self) -> dict[str, Any]:
        return {"num_ctx": self.num_ctx, "temperature": self.temperature}

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http.post(path, json=body)
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"Ollama unreachable: {exc}") from exc
        _raise_for_status(response)
        return response.json()


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise ModelUnavailable(f"Ollama returned HTTP {response.status_code}")


def _reply(content: str, wire_calls: list[dict[str, Any]], tools: list[ToolSpec]) -> ModelReply:
    """The model's message as a ModelReply: its tool calls, else any call written as text,
    else its text."""
    names = {name: t.name for t in tools for name in (t.name, _legacy_name(t.name))}
    content = content.strip()
    calls = tuple(
        ToolCall(
            id=f"call_{uuid4().hex[:8]}",
            name=names.get(fn.get("name", ""), fn.get("name", "")),
            arguments=_arguments(fn.get("arguments")),
        )
        for fn in (c.get("function") or {} for c in wire_calls)
    )
    if not calls and tools:
        calls = _calls_in_text(content, names)
    if calls:
        return ModelReply(text=None, tool_calls=calls)
    return ModelReply(text=content)


def _may_be_text_call(content: str) -> bool:
    """Whether text so far could still be the start of a tool call written as text."""
    start = content.lstrip()[: len(TOOL_CALL_OPEN)]
    return not start or start.startswith("{") or TOOL_CALL_OPEN.startswith(start)


def _legacy_name(name: str) -> str:
    """The `server__tool` form a model may still use for a tool."""
    return name.replace(".", "__")


def _tool_to_wire(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.input_schema,
        },
    }


def _to_wire(message: Message) -> dict[str, Any]:
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        wire["tool_calls"] = [
            {"function": {"name": c.name, "arguments": c.arguments}} for c in message.tool_calls
        ]
    return wire


def _arguments(raw: Any) -> dict[str, Any]:
    """Arguments arrive as an object, or sometimes as a JSON string."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _calls_in_text(content: str, names: dict[str, str]) -> tuple[ToolCall, ...]:
    """Tool calls the model wrote as text: `<tool_call>{...}</tool_call>` or a bare JSON object.

    Only a call to one of the offered tools counts, so an answer that happens to contain JSON is
    left as text.
    """
    tagged = TOOL_CALL_TAGS.findall(content)
    candidates = tagged or ([content] if content.startswith("{") and content.endswith("}") else [])
    calls = []
    for raw in candidates:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return ()
        name = obj.get("name") if isinstance(obj, dict) else None
        tool = names.get(name or "") or (name if name in names.values() else None)
        if tool is None:
            return ()
        args = obj.get("arguments", obj.get("parameters"))
        calls.append(ToolCall(f"call_{uuid4().hex[:8]}", tool, _arguments(args)))
    return tuple(calls)
