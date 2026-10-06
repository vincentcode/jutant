"""The tracing port, a tracer that records nothing, and `Trace`, which the core works with.

A span is one step of a turn (routing, a model call, a tool call) with its attributes. Spans
are given their parent explicitly rather than through ambient context: a turn is an async
generator that pauses between events, and ambient context does not survive those pauses.

A trace crosses processes as a carrier, a few strings (W3C `traceparent`) a span gives with
`carrier()` and a tracer turns back into a parent with `remote()`: a tool call passes its span
to the MCP server, whose spans then join the same trace.

Attribute keys are the core's own; a provider translates them to its backend's conventions:

    session, user, role          who is asking, in which conversation
    input, output                what went in and came out (text only if content is traced)
    model                        the model's name
    messages                     [{role, content}] sent to the model
    reply, reply.tool_calls      the model's text, or the [{name, arguments}] it called
    tokens.prompt, tokens.completion
    tool.name, tool.arguments, tool.ok, tool.error
    anything else                a plain value, shown as is (feature, routed_by, step...)
"""

from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Literal, Protocol

from core.observability.content import TraceContent

SpanKind = Literal["agent", "chain", "llm", "tool", "retriever", "embedding"]


class Span(Protocol):
    def set(self, attributes: Mapping[str, Any]) -> None: ...
    def fail(self, reason: str) -> None: ...
    def carrier(self) -> dict[str, str]:
        """This span as strings another process can continue the trace from."""
        ...


class Tracer(Protocol):
    def span(
        self,
        name: str,
        kind: SpanKind,
        attributes: Mapping[str, Any],
        parent: Span | None,
    ) -> AbstractContextManager[Span]:
        """A span, open while the block runs; `parent` None starts a new trace. An exception
        leaving the block marks the span failed and is re-raised."""
        ...

    def remote(self, carrier: Mapping[str, str]) -> Span | None:
        """A parent for spans continuing a trace begun in another process, or None."""
        ...


class _NoopSpan:
    def set(self, attributes: Mapping[str, Any]) -> None:
        pass

    def fail(self, reason: str) -> None:
        pass

    def carrier(self) -> dict[str, str]:
        return {}


class NoopTracer:
    @contextmanager
    def span(
        self, name: str, kind: SpanKind, attributes: Mapping[str, Any], parent: Span | None
    ) -> Iterator[Span]:
        yield _NoopSpan()

    def remote(self, carrier: Mapping[str, str]) -> Span | None:
        return None


NOOP = NoopTracer()


class Trace:
    """Where the core records spans: a tracer, what content may be recorded, and the span new
    spans hang under. Attributes whose value is None are left out, so content that may not be
    traced is simply not passed on."""

    def __init__(
        self,
        tracer: Tracer = NOOP,
        content: TraceContent | None = None,
        span: Span | None = None,
    ):
        self.tracer = tracer
        self.content = content or TraceContent()
        self._span = span

    @contextmanager
    def span(self, name: str, kind: SpanKind, **attributes: Any) -> Iterator["Trace"]:
        with self.tracer.span(name, kind, _present(attributes), self._span) as span:
            yield Trace(self.tracer, self.content, span)

    def set(self, **attributes: Any) -> None:
        if self._span is not None:
            self._span.set(_present(attributes))

    def fail(self, reason: str) -> None:
        if self._span is not None:
            self._span.fail(reason)

    def carrier(self) -> dict[str, str]:
        """The current span, for another process to continue the trace from."""
        return self._span.carrier() if self._span is not None else {}

    @classmethod
    def continuing(
        cls, tracer: Tracer, carrier: Mapping[str, Any] | None, content: TraceContent | None = None
    ) -> "Trace":
        """A trace whose spans join the one `carrier` came from (a new one if it is empty)."""
        valid = {k: v for k, v in (carrier or {}).items() if isinstance(v, str)}
        return cls(tracer, content, tracer.remote(valid) if valid else None)

    def text(self, value: Any) -> Any:
        """`value` masked, if content may be traced; else None, so it is left out."""
        return self.content.text(value)

    def masked(self, value: Any) -> Any:
        """`value` masked, always recorded (tool arguments, as in the audit log)."""
        return self.content.masked(value)


def _present(attributes: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in attributes.items() if v is not None}
