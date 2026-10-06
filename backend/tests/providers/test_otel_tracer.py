"""OtelTracer: the core's spans as OpenTelemetry spans with OpenInference attributes."""

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from core.observability import Trace, TraceContent
from providers.tracing.otel import OtelTracer, translate


def recording() -> tuple[OtelTracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    return OtelTracer("http://unused", exporter=exporter, project="jutant-test"), exporter


def test_spans_nest_by_explicit_parent_and_carry_openinference_attributes() -> None:
    tracer, exporter = recording()
    trace = Trace(tracer, TraceContent(include=True))
    with trace.span("turn", "agent", session="c-1", user="S0042", input="KYC?") as turn:
        with turn.span(
            "model",
            "llm",
            model="qwen2.5:7b",
            messages=[{"role": "user", "content": "KYC?"}],
        ) as llm:
            llm.set(**{"reply": "Two IDs.", "tokens.prompt": 120, "tokens.completion": 8})
        with turn.span(
            "documents.search",
            "tool",
            **{"tool.name": "documents.search", "tool.arguments": {"query": "KYC"}},
        ):
            pass
    tracer.shutdown()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    root, llm_span, tool = spans["turn"], spans["model"], spans["documents.search"]
    assert root.parent is None
    assert llm_span.parent.span_id == root.context.span_id
    assert tool.parent.span_id == root.context.span_id
    assert root.attributes["openinference.span.kind"] == "AGENT"
    assert root.attributes["session.id"] == "c-1" and root.attributes["user.id"] == "S0042"
    assert root.resource.attributes["openinference.project.name"] == "jutant-test"
    assert llm_span.attributes["llm.model_name"] == "qwen2.5:7b"
    assert llm_span.attributes["llm.input_messages.0.message.content"] == "KYC?"
    assert llm_span.attributes["llm.output_messages.0.message.content"] == "Two IDs."
    assert llm_span.attributes["llm.token_count.total"] == 128
    assert tool.attributes["openinference.span.kind"] == "TOOL"
    assert tool.attributes["tool.parameters"] == '{"query": "KYC"}'


def test_a_turn_paused_between_events_keeps_its_children() -> None:
    """A turn is an async generator: spans open across its pauses must still nest."""
    tracer, exporter = recording()

    def turn():
        with Trace(tracer).span("turn", "agent") as t:
            yield "first event"
            with t.span("model", "llm"):
                yield "second event"

    events = turn()
    next(events)
    with Trace(tracer).span("other request", "agent"):  # another turn runs meanwhile
        pass
    next(events)
    events.close()  # the client went away
    tracer.shutdown()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["model"].parent.span_id == spans["turn"].context.span_id
    assert spans["other request"].parent is None
    assert spans["turn"].attributes["jutant.stopped"] is True  # stopped, not failed
    assert spans["turn"].status.is_ok


def test_an_error_marks_the_span_failed() -> None:
    tracer, exporter = recording()
    with pytest.raises(RuntimeError), Trace(tracer).span("turn", "agent"):
        raise RuntimeError("boom")
    with Trace(tracer).span("refused", "agent") as t:
        t.fail("denied")
    tracer.shutdown()
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert not spans["turn"].status.is_ok
    assert spans["refused"].status.description == "denied"


def test_other_attributes_keep_their_values_under_a_jutant_prefix() -> None:
    out = translate({"routed_by": "pattern", "score": 0.91, "step": 3, "tools": ["a", "b"]})
    assert out == {
        "jutant.routed_by": "pattern",
        "jutant.score": 0.91,
        "jutant.step": 3,
        "jutant.tools": '["a", "b"]',
    }
