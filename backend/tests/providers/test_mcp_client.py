"""McpToolClient against real MCP servers running in-process: no network needed."""

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import Context, MCPServer

from core.events import Completed
from core.policy.identity import verify_caller
from core.tools import envelope
from core.types import Caller, Citation, ModelReply, ToolCall
from providers.llm.fake import FakeModel
from providers.mcp.client import McpToolClient
from tests.builders import collect_events, make_rig, teller

SECRET = "test-secret"


def documents_server(seen: list[Caller]) -> MCPServer:
    server = MCPServer("documents")

    @server.tool(name="search", description="Search documents.")
    async def search(query: str, ctx: Context, limit: int = 4) -> dict[str, Any]:
        meta = ctx.request_context.meta or {}
        caller = verify_caller(meta[envelope.CALLER_META_KEY], SECRET)
        seen.append(caller)
        if query == "secret":
            return envelope.error("denied")
        return envelope.ok(
            [{"title": "KYC Policy", "section": "4.2", "text": f"About {query}."}],
            [Citation("document", "KYC Policy", "4.2")],
        )

    @server.tool(name="crash")
    async def crash(x: int) -> dict[str, Any]:
        raise RuntimeError("database down")

    return server


@asynccontextmanager
async def connected():
    """A client on the documents server, and the callers the server saw.

    Opened inside each test rather than as a fixture: the SDK's task scopes must close in the
    task that opened them, and async fixtures tear down in a different one.
    """
    seen: list[Caller] = []
    async with McpToolClient({"documents": documents_server(seen)}, SECRET) as client:
        yield client, seen


async def test_tools_are_listed_with_the_server_prefix() -> None:
    async with connected() as (client, _):
        specs = {s.name: s for s in await client.list_tools()}
    assert set(specs) == {"documents.search", "documents.crash"}
    assert specs["documents.search"].input_schema["required"] == ["query"]
    assert specs["documents.search"].description == "Search documents."


async def test_call_carries_a_verified_caller_and_reads_the_envelope() -> None:
    caller = teller()
    async with connected() as (client, seen):
        result = await client.call(caller, ToolCall("7", "documents.search", {"query": "kyc"}))
    assert result.ok and result.call_id == "7"
    assert result.data[0]["text"] == "About kyc."
    assert result.citations == (Citation("document", "KYC Policy", "4.2"),)
    assert seen == [caller]


async def test_denied_envelope() -> None:
    async with connected() as (client, _):
        result = await client.call(teller(), ToolCall("1", "documents.search", {"query": "secret"}))
    assert (result.ok, result.error) == (False, "denied")


async def test_bad_arguments_and_crashes_are_reported() -> None:
    async with connected() as (client, _):
        bad = await client.call(teller(), ToolCall("1", "documents.search", {"limit": 2}))
        crashed = await client.call(teller(), ToolCall("2", "documents.crash", {"x": 1}))
    assert bad.error == "invalid_arguments"
    assert crashed.error == "upstream_error"


async def test_unknown_server_or_tool() -> None:
    async with connected() as (client, _):
        assert (await client.call(teller(), ToolCall("1", "ledger.get", {}))).error == "not_found"
        assert (await client.call(teller(), ToolCall("1", "documents", {}))).error == "not_found"


async def test_wrong_secret_never_reaches_the_tool() -> None:
    seen: list[Caller] = []
    async with McpToolClient({"documents": documents_server(seen)}, "other-secret") as c:
        result = await c.call(teller(), ToolCall("1", "documents.search", {"query": "kyc"}))
    assert not result.ok
    assert seen == []


async def test_orchestrator_turn_through_a_real_mcp_server() -> None:
    """The whole path: orchestrator -> gateway -> MCP client -> server tool -> envelope."""
    seen: list[Caller] = []
    model = FakeModel(
        replies=[
            ModelReply(None, (ToolCall("1", "documents.search", {"query": "joint accounts"}),)),
            ModelReply("Both holders must provide ID."),
        ]
    )
    async with McpToolClient({"documents": documents_server(seen)}, SECRET) as tools:
        rig = await make_rig(model, specs=[])
        rig.orchestrator.gateway.client = tools
        rig.orchestrator.gateway.catalog.client = tools
        await rig.orchestrator.load_tools()

        events = await collect_events(
            rig.orchestrator.ask(teller(), uuid4(), "KYC for joint accounts?", "policy_qa")
        )

    answer = events[-1]
    assert isinstance(answer, Completed)
    assert answer.answer.citations == (Citation("document", "KYC Policy", "4.2"),)
    assert seen == [teller()]
