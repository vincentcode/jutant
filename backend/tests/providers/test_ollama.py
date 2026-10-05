"""OllamaProvider against a fake Ollama server (httpx.MockTransport): no model needed."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from core.errors import ModelUnavailable
from core.types import Message, ModelReply, ToolCall, ToolSpec
from providers.llm.ollama import OllamaProvider

SEARCH = ToolSpec("documents.search", "Search documents.", {"type": "object"})


def provider(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaProvider:
    return OllamaProvider(
        base_url="http://ollama:11434",
        model="qwen2.5:7b",
        embed_model="nomic-embed-text",
        num_ctx=8192,
        transport=httpx.MockTransport(handler),
    )


def replying(message: dict[str, Any], seen: list[dict[str, Any]] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", **message}, "done": True})

    return handler


async def test_chat_sends_options_tools_and_history() -> None:
    seen: list[dict[str, Any]] = []
    model = provider(replying({"content": "Hello."}, seen))
    history = [
        Message("system", "Be brief."),
        Message("assistant", "", tool_calls=(ToolCall("1", "documents.search", {"query": "kyc"}),)),
        Message("tool", '{"ok":true}', tool_call_id="1"),
    ]

    reply = await model.chat(history, [SEARCH])

    assert reply.text == "Hello." and reply.tool_calls == ()
    body = seen[0]
    assert body["model"] == "qwen2.5:7b"
    assert body["options"] == {"num_ctx": 8192, "temperature": 0.1}
    assert body["stream"] is False
    assert body["tools"][0]["function"]["name"] == "documents.search"  # as the prompts name it
    assert body["messages"][1]["tool_calls"][0]["function"] == {
        "name": "documents.search",
        "arguments": {"query": "kyc"},
    }


async def test_no_tools_key_when_no_tools_are_offered() -> None:
    seen: list[dict[str, Any]] = []
    await provider(replying({"content": "policy_qa"}, seen)).chat([Message("user", "hi")], [])
    assert "tools" not in seen[0]


async def test_tool_calls_are_read_with_dotted_or_legacy_names() -> None:
    model = provider(
        replying(
            {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "documents.search", "arguments": {"query": "kyc"}}},
                    {"function": {"name": "documents__search", "arguments": '{"query": "aml"}'}},
                ],
            }
        )
    )
    reply = await model.chat([Message("user", "kyc?")], [SEARCH])
    assert reply.text is None
    assert [(c.name, c.arguments) for c in reply.tool_calls] == [
        ("documents.search", {"query": "kyc"}),
        ("documents.search", {"query": "aml"}),
    ]
    assert reply.tool_calls[0].id != reply.tool_calls[1].id


@pytest.mark.parametrize(
    "content",
    [
        '<tool_call>\n{"name": "documents__search", "arguments": {"query": "kyc"}}\n</tool_call>',
        '{"name": "documents.search", "arguments": {"query": "kyc"}}',
    ],
)
async def test_tool_call_written_as_text_is_recognised(content: str) -> None:
    reply = await provider(replying({"content": content})).chat([Message("user", "kyc?")], [SEARCH])
    assert [(c.name, c.arguments) for c in reply.tool_calls] == [
        ("documents.search", {"query": "kyc"})
    ]


async def test_json_answer_naming_no_offered_tool_stays_text() -> None:
    content = '{"name": "Ama", "id_number": "GHA-1"}'
    reply = await provider(replying({"content": content})).chat([Message("user", "x")], [SEARCH])
    assert reply.text == content and reply.tool_calls == ()


async def test_embed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        body = json.loads(request.content)
        assert body == {"model": "nomic-embed-text", "input": ["a", "b"]}
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    assert await provider(handler).embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


def streaming(*messages: dict[str, Any]):
    lines = [{"message": m, "done": False} for m in messages] + [{"message": {}, "done": True}]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True and body["tools"][0]["function"]["name"] == "documents.search"
        return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())

    return handler


async def stream_parts(handler) -> list[Any]:
    model = provider(handler)
    return [p async for p in model.stream_chat([Message("user", "kyc?")], [SEARCH])]


async def test_stream_chat_passes_text_on_as_it_arrives() -> None:
    parts = await stream_parts(
        streaming({"content": "\n Both "}, {"content": "holders "}, {"content": "sign."})
    )
    assert parts[:-1] == ["Both ", "holders ", "sign."]
    assert parts[-1] == ModelReply(text="Both holders sign.")


async def test_stream_chat_tool_call_yields_no_text() -> None:
    call = {"function": {"name": "documents.search", "arguments": {"query": "kyc"}}}
    parts = await stream_parts(streaming({"content": "", "tool_calls": [call]}))
    assert len(parts) == 1
    assert [(c.name, c.arguments) for c in parts[0].tool_calls] == [
        ("documents.search", {"query": "kyc"})
    ]


async def test_stream_chat_holds_back_a_tool_call_written_as_text() -> None:
    parts = await stream_parts(
        streaming(
            {"content": "<tool"},
            {"content": '_call>{"name": "documents.search", '},
            {"content": '"arguments": {"query": "kyc"}}</tool_call>'},
        )
    )
    assert len(parts) == 1 and parts[0].tool_calls[0].name == "documents.search"


async def test_stream_chat_releases_text_that_only_looked_like_a_call() -> None:
    parts = await stream_parts(streaming({"content": "<"}, {"content": "b>Note</b>"}))
    assert parts[:-1] == ["<b>Note</b>"]


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500),
        lambda request: httpx.Response(404, json={"error": "model not found"}),
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused")),
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
    ],
    ids=["server_error", "model_missing", "unreachable", "timeout"],
)
async def test_failures_raise_model_unavailable(handler) -> None:
    with pytest.raises(ModelUnavailable):
        await provider(handler).chat([Message("user", "hi")], [])
