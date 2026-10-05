import pytest

from core.errors import InvalidToolCall, UnknownTool
from core.tools.catalog import ToolCatalog
from core.tools.gateway import ToolGateway
from core.types import Caller, Feature, ToolCall, ToolResult, ToolSpec
from providers.mcp.fake import FakeToolClient
from tests.fakes import InMemoryAudit

SEARCH_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
    "required": ["query"],
    "additionalProperties": False,
}
FEATURE = Feature("qa", "document_qa", "Q&A", "", "", ("documents.search",), ())


async def make_gateway(result: ToolResult | None = None):
    tools = FakeToolClient(
        results={"documents.search": result or ToolResult("", ok=True, data=[])},
        specs=[
            ToolSpec("documents.search", "Search", SEARCH_SCHEMA),
            ToolSpec("records.get", "Get", {"type": "object"}),
        ],
    )
    catalog = ToolCatalog(tools)
    await catalog.load()
    audit = InMemoryAudit()
    return ToolGateway(tools, catalog, audit), tools, audit


async def test_valid_call_reaches_the_client_with_the_caller(teller: Caller) -> None:
    gateway, tools, audit = await make_gateway()
    result = await gateway.execute(
        teller, FEATURE, ToolCall("1", "documents.search", {"query": "kyc"})
    )
    assert result.ok
    assert tools.calls[0].caller == teller
    assert audit.names() == ["tool_called"]


async def test_tool_not_in_feature_is_rejected(teller: Caller) -> None:
    gateway, tools, audit = await make_gateway()
    with pytest.raises(InvalidToolCall):
        await gateway.execute(teller, FEATURE, ToolCall("1", "records.get", {}))
    assert tools.calls == []
    assert audit.names() == ["tool_failed"]


async def test_unknown_tool_is_rejected(teller: Caller) -> None:
    gateway, _, _ = await make_gateway()
    feature = Feature("qa", "document_qa", "Q&A", "", "", ("documents.delete",), ())
    with pytest.raises(UnknownTool):
        await gateway.execute(teller, feature, ToolCall("1", "documents.delete", {}))


async def test_invalid_arguments_come_back_as_a_result(teller: Caller) -> None:
    gateway, tools, audit = await make_gateway()
    result = await gateway.execute(
        teller, FEATURE, ToolCall("1", "documents.search", {"limit": "4"})
    )
    assert not result.ok
    assert result.error == "invalid_arguments"
    assert any("query" in p for p in result.data["problems"])
    assert tools.calls == []
    assert audit.names() == ["tool_failed"]


async def test_identity_arguments_are_stripped(teller: Caller) -> None:
    gateway, tools, _ = await make_gateway()
    call = ToolCall("1", "documents.search", {"query": "kyc", "user_id": "admin", "role": "x"})
    result = await gateway.execute(teller, FEATURE, call)
    assert result.ok
    assert tools.calls[0].call.arguments == {"query": "kyc"}


async def test_denied_result_is_audited_as_denied(teller: Caller) -> None:
    gateway, _, audit = await make_gateway(ToolResult("", ok=False, error="denied"))
    result = await gateway.execute(
        teller, FEATURE, ToolCall("1", "documents.search", {"query": "x"})
    )
    assert result.error == "denied"
    assert audit.names() == ["tool_denied"]
