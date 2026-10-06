"""Tracing: what happened in a turn, step by step, for a tracing backend such as Phoenix.

The core records spans through the `Tracer` port and never imports a tracing library; the
deployment plugs one in (`providers/tracing`). Without one, `NOOP` records nothing.
"""

from core.observability.content import TraceContent
from core.observability.model import TracedModel
from core.observability.tracer import NOOP, NoopTracer, Span, SpanKind, Trace, Tracer

__all__ = [
    "NOOP",
    "NoopTracer",
    "Span",
    "SpanKind",
    "Trace",
    "TraceContent",
    "TracedModel",
    "Tracer",
]
