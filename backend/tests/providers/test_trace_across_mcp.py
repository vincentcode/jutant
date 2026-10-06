"""A tool call's trace continues inside the MCP server: one trace from question to bank call."""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from core.observability import Trace, TraceContent
from core.policy.engine import PolicyEngine
from core.policy.rules import Decision, FunctionRule
from core.types import ToolCall
from mcp_servers.documents.tools import create_server
from providers.mcp.client import McpToolClient
from providers.tracing.otel import OtelTracer
from tests.mcp_servers.test_documents import ENGINE, LABELS, SECRET, MemoryStore, teller


async def traced_call(arguments: dict, engine=ENGINE):
    exporter = InMemorySpanExporter()
    tracer = OtelTracer("http://unused", exporter=exporter)
    server = create_server(MemoryStore(), engine, SECRET, lambda role: LABELS[role])
    server.tracer = tracer  # as `serve` sets it from the environment
    async with McpToolClient({"documents": server.mcp}, SECRET) as client:
        with Trace(tracer, TraceContent()).span("documents.search", "tool") as tool_span:
            result = await client.call(
                teller(),
                ToolCall("1", "documents.search", arguments),
                tool_span.carrier(),
            )
    tracer.shutdown()
    return result, {s.name: s for s in exporter.get_finished_spans()}


async def test_the_server_s_spans_join_the_platform_s_trace() -> None:
    result, spans = await traced_call({"query": "holders, account 0011223344"})

    assert result.ok
    platform = spans["documents.search"]
    server = spans["documents.search (server)"]
    tool_run = [
        s for s in spans.values() if s.parent and s.parent.span_id == server.context.span_id
    ]
    assert server.context.trace_id == platform.context.trace_id  # one trace
    assert server.parent.span_id == platform.context.span_id  # under the platform's tool call
    assert server.attributes["user.id"] == "S1"
    assert server.attributes["jutant.policy.arguments"] == "allowed"
    assert "******3344" in server.attributes["tool.parameters"]  # masked, as in the audit log
    assert "0011223344" not in server.attributes["tool.parameters"]
    assert [s.name for s in tool_run] == ["documents.search handler"]  # the tool's own run


async def test_a_refusal_in_the_server_is_traced_as_one() -> None:
    refusing = PolicyEngine(
        [FunctionRule("documents.search", lambda c, a, r: Decision(False, "role"))]
    )
    result, spans = await traced_call({"query": "anything"}, refusing)

    assert result.error == "denied"
    server = spans["documents.search (server)"]
    assert server.attributes["jutant.policy.arguments"] == "denied: role"
    assert server.status.description == "denied"
    children = [
        s for s in spans.values() if s.parent and s.parent.span_id == server.context.span_id
    ]
    assert children == []  # the tool never ran
