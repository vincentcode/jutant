"""OtelTracer: implements the core's tracing port with OpenTelemetry, exporting over OTLP/HTTP.

Spans are named with OpenInference attributes (`openinference.span.kind`, `llm.input_messages`,
`tool.name`...), which Phoenix and other LLM tracing tools read; the core's own attribute keys
are translated here, so the core knows nothing of either. Spans are exported in batches in the
background: a tracing backend that is down costs a log line, never a slow answer.
"""

import json
import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Status, StatusCode

from core.observability import SpanKind

logger = logging.getLogger(__name__)

STOPPED = (GeneratorExit,)  # the client went away: the turn ended early, it did not fail


class _Span:
    def __init__(self, span: trace.Span):
        self.otel = span

    def set(self, attributes: Mapping[str, Any]) -> None:
        self.otel.set_attributes(translate(attributes))

    def fail(self, reason: str) -> None:
        self.otel.set_status(Status(StatusCode.ERROR, reason))


class OtelTracer:
    def __init__(
        self,
        endpoint: str,
        *,
        api_key: str = "",
        service_name: str = "jutant",
        project: str = "jutant",
        exporter: SpanExporter | None = None,
    ):
        """`endpoint` is the OTLP/HTTP traces URL, e.g. http://phoenix:6006/v1/traces;
        `project` is the Phoenix project the traces are filed under."""
        resource = Resource.create(
            {"service.name": service_name, "openinference.project.name": project}
        )
        self._provider = TracerProvider(resource=resource)
        headers = {"authorization": f"Bearer {api_key}"} if api_key else None
        self._provider.add_span_processor(
            BatchSpanProcessor(exporter or OTLPSpanExporter(endpoint=endpoint, headers=headers))
        )
        self._tracer = self._provider.get_tracer("jutant")

    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanKind,
        attributes: Mapping[str, Any],
        parent: Any,
    ) -> Iterator[_Span]:
        # The parent is passed explicitly and nothing is made "current": a turn pauses between
        # events, and context attached before a pause cannot be detached cleanly after it.
        parent_span = parent.otel if isinstance(parent, _Span) else None
        context = (
            trace.set_span_in_context(parent_span)
            if parent_span is not None
            else otel_context.Context()  # a new trace
        )
        span = self._tracer.start_span(name, context=context)
        span.set_attribute("openinference.span.kind", kind.upper())
        span.set_attributes(translate(attributes))
        try:
            yield _Span(span)
        except STOPPED:
            span.set_attribute("jutant.stopped", True)
            raise
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise
        finally:
            span.end()

    def shutdown(self) -> None:
        """Send any spans still waiting, then stop."""
        self._provider.shutdown()


def translate(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """The core's attribute keys as OpenInference attributes, flattened to values OTLP takes."""
    out: dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        match key:
            case "input" | "output":
                out[f"{key}.value"] = _text(value)
                out[f"{key}.mime_type"] = (
                    "text/plain" if isinstance(value, str) else "application/json"
                )
            case "session":
                out["session.id"] = str(value)
            case "user":
                out["user.id"] = str(value)
            case "model":
                out["llm.model_name"] = str(value)
            case "messages":
                for i, message in enumerate(value):
                    out[f"llm.input_messages.{i}.message.role"] = str(message["role"])
                    out[f"llm.input_messages.{i}.message.content"] = str(message["content"])
            case "reply":
                out["llm.output_messages.0.message.role"] = "assistant"
                out["llm.output_messages.0.message.content"] = str(value)
                out["output.value"] = str(value)
            case "reply.tool_calls":
                out["llm.output_messages.0.message.role"] = "assistant"
                for i, call in enumerate(value):
                    prefix = f"llm.output_messages.0.message.tool_calls.{i}.tool_call.function"
                    out[f"{prefix}.name"] = str(call["name"])
                    out[f"{prefix}.arguments"] = _text(call["arguments"])
                out["output.value"] = _text(value)
            case "tokens.prompt":
                out["llm.token_count.prompt"] = int(value)
            case "tokens.completion":
                out["llm.token_count.completion"] = int(value)
            case "tool.name":
                out["tool.name"] = str(value)
            case "tool.arguments":
                out["tool.parameters"] = _text(value)
                out["input.value"] = _text(value)
                out["input.mime_type"] = "application/json"
            case _:
                out[f"jutant.{key}"] = (
                    value if isinstance(value, str | bool | int | float) else _text(value)
                )
    if "llm.token_count.prompt" in out and "llm.token_count.completion" in out:
        out["llm.token_count.total"] = (
            out["llm.token_count.prompt"] + out["llm.token_count.completion"]
        )
    return out


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
