"""Tracing backends for the core's Tracer port."""

from typing import Any

from core.observability import NOOP, Tracer


def build(settings: Any) -> Tracer:
    """OpenTelemetry to JUTANT_TRACING_ENDPOINT if it is set; otherwise nothing is traced."""
    if not settings.JUTANT_TRACING_ENDPOINT:
        return NOOP
    from providers.tracing.otel import OtelTracer

    return OtelTracer(
        settings.JUTANT_TRACING_ENDPOINT,
        api_key=settings.JUTANT_TRACING_API_KEY,
        service_name=settings.JUTANT_TRACING_SERVICE_NAME,
        project=settings.JUTANT_TRACING_PROJECT,
    )
