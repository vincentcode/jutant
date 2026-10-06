"""Tracing backends for the core's Tracer port."""

import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from core.observability import NOOP, TraceContent, Tracer

if TYPE_CHECKING:
    from providers.tracing.feedback import FeedbackSink


def build(settings: Any) -> Tracer:
    """OpenTelemetry to JUTANT_TRACING_ENDPOINT if it is set; otherwise nothing is traced."""
    return _tracer(
        settings.JUTANT_TRACING_ENDPOINT,
        settings.JUTANT_TRACING_API_KEY,
        settings.JUTANT_TRACING_SERVICE_NAME,
        settings.JUTANT_TRACING_PROJECT,
    )


def from_env(service_name: str, env: Mapping[str, str] = os.environ) -> tuple[Tracer, TraceContent]:
    """The tracer and content rule for a process without Django settings (an MCP server),
    from the same JUTANT_TRACING_* and JUTANT_TRACE_CONTENT variables the API reads."""
    tracer = _tracer(
        env.get("JUTANT_TRACING_ENDPOINT", ""),
        env.get("JUTANT_TRACING_API_KEY", ""),
        service_name,
        env.get("JUTANT_TRACING_PROJECT", "jutant"),
    )
    content = env.get("JUTANT_TRACE_CONTENT", "false").lower() in ("1", "true", "yes")
    return tracer, TraceContent(include=content)


def _tracer(endpoint: str, api_key: str, service_name: str, project: str) -> Tracer:
    if not endpoint:
        return NOOP
    from providers.tracing.otel import OtelTracer

    return OtelTracer(endpoint, api_key=api_key, service_name=service_name, project=project)


def feedback_sink(settings: Any) -> "FeedbackSink":
    """Where staff feedback on answers goes besides the database: Phoenix, when traces go to
    Phoenix (JUTANT_TRACING_FEEDBACK=phoenix, the default) and its address can be told from
    the traces endpoint; otherwise nowhere."""
    from providers.tracing.feedback import NoFeedbackSink, PhoenixFeedback, phoenix_base

    base = phoenix_base(settings.JUTANT_TRACING_ENDPOINT or "")
    if settings.JUTANT_TRACING_FEEDBACK != "phoenix" or base is None:
        return NoFeedbackSink()
    return PhoenixFeedback(base, settings.JUTANT_TRACING_API_KEY)
