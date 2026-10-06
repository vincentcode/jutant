"""GuardedServer: an MCP server whose every tool passes the policy engine.

The MCP server is the trust boundary: whatever the platform or the model asks for, a tool only
runs, and only returns data, if the access rules allow it. Each tool registered with
`GuardedServer.tool` is wrapped so that a call:

1. resolves the caller from the signed token in the request (no valid token: `denied`);
2. is authorised on its arguments (no rule for the tool, or the rule refuses: `denied`);
3. runs the tool, which returns a `ToolOutput`;
4. is authorised again on the fetched record, if the tool returned one, for scope checks such
   as "same branch" that need to see the record;
5. has hidden fields removed from its data;
6. returns the shared envelope with the data and citations.

With a tracer set, each call is a span that joins the platform's trace (from the call's
`_meta`): who called, every policy decision, and the tool's own run (its calls to the client's
systems) as a child span. Arguments are masked as in the audit log; the returned data is traced
only with content tracing on.

A tool function takes the verified `caller` as its first parameter, followed by the arguments
the model supplies. The caller parameter is left out of the schema the model sees.
"""

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from mcp.server.mcpserver import Context, MCPServer

from core.errors import PolicyDenied
from core.observability import NOOP, Trace, TraceContent, Tracer
from core.policy.engine import PolicyEngine
from core.policy.rules import Decision
from core.tools import envelope
from core.types import Citation
from mcp_servers.common.auth import caller_from_context

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolOutput:
    data: Any
    citations: tuple[Citation, ...] = ()
    record: dict[str, Any] | None = (
        None  # what scope rules check, e.g. the account the rows are for
    )


class ToolInputError(Exception):
    """Raised by a tool for arguments that pass the schema but make no sense (a bad date)."""


ToolFn = Callable[..., Awaitable[ToolOutput]]


class GuardedServer:
    def __init__(
        self,
        name: str,
        engine: PolicyEngine,
        secret: str,
        tracer: Tracer = NOOP,
        trace_content: TraceContent | None = None,
    ):
        self.name = name
        self.engine = engine
        self.secret = secret
        self.tracer = tracer  # set by the process serving it (`serve`), if tracing is on
        self.trace_content = trace_content or TraceContent()
        self.mcp = MCPServer(name)
        self.guarded: set[str] = set()

    def tool(self, name: str, description: str) -> Callable[[ToolFn], ToolFn]:
        """Register `fn` as the tool `name`, behind the guard. Returns `fn` unchanged."""

        def decorate(fn: ToolFn) -> ToolFn:
            qualified = f"{self.name}.{name}"
            hints = get_type_hints(fn)
            params = [
                p.replace(annotation=hints.get(p.name, p.annotation))
                for p in inspect.signature(fn).parameters.values()
                if p.name != "caller"
            ]

            async def handler(ctx: Context, **arguments: Any) -> dict[str, Any]:
                return await self._run(qualified, fn, ctx, arguments)

            ctx_param = inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=Context)
            handler.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
                [*params, ctx_param], return_annotation=dict[str, Any]
            )
            handler.__annotations__ = {
                **{p.name: p.annotation for p in params},
                "ctx": Context,
                "return": dict[str, Any],
            }
            self.mcp.add_tool(handler, name=name, description=description)
            self.guarded.add(name)
            return fn

        return decorate

    async def _run(
        self, qualified: str, fn: ToolFn, ctx: Context, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        meta = ctx.request_context.meta or {}
        carrier = meta.get(envelope.TRACE_META_KEY) if isinstance(meta, dict) else None
        trace = Trace.continuing(
            self.tracer, carrier if isinstance(carrier, dict) else None, self.trace_content
        )
        attributes = {"tool.name": qualified, "tool.arguments": trace.masked(arguments)}
        with trace.span(f"{qualified} (server)", "tool", **attributes) as span:
            result = await self._guarded(qualified, fn, ctx, arguments, span)
            span.set(**{"tool.ok": result["ok"], "tool.error": result.get("error")})
            if not result["ok"]:
                span.fail(result["error"])
            return result

    async def _guarded(
        self, qualified: str, fn: ToolFn, ctx: Context, arguments: dict[str, Any], span: Trace
    ) -> dict[str, Any]:
        try:
            caller = caller_from_context(ctx, self.secret)
        except PolicyDenied as exc:
            logger.warning("%s refused: %s", qualified, exc)
            span.set(refused="no valid caller token")
            return envelope.error("denied")
        span.set(user=caller.id, role=caller.role)

        decision = self.engine.authorize(caller, qualified, arguments)
        span.set(**{"policy.arguments": _verdict(decision)})
        if not decision.allow:
            logger.info("%s denied for %s: %s", qualified, caller.id, decision.reason)
            return envelope.error("denied")

        with span.span(f"{qualified} handler", "chain") as run:  # the tool: the client's systems
            try:
                output = await fn(caller, **arguments)
            except LookupError:
                run.set(error="not_found")
                return envelope.error("not_found")
            except ToolInputError as exc:
                run.set(error="invalid_arguments")
                return envelope.error("invalid_arguments", [str(exc)])
            except PolicyDenied:
                run.set(error="denied")
                return envelope.error("denied")
            except Exception as exc:
                logger.exception("%s failed", qualified)
                run.fail(type(exc).__name__)
                return envelope.error("upstream_error")

        if output.record is not None:
            decision = self.engine.authorize(caller, qualified, arguments, record=output.record)
            span.set(**{"policy.record": _verdict(decision)})
            if not decision.allow:
                logger.info("%s denied on record for %s: %s", qualified, caller.id, decision.reason)
                return envelope.error("denied")

        data = self.engine.filter(caller, qualified, output.data)
        span.set(output=span.text(data), citations=len(output.citations))
        return envelope.ok(data, output.citations)

    async def tool_names(self) -> list[str]:
        """Every tool the server offers, as `<server>.<tool>`."""
        return sorted(f"{self.name}.{t.name}" for t in await self.mcp.list_tools())

    async def unguarded_tools(self) -> list[str]:
        """Tools registered on the MCP server without going through `tool()`. Should be none."""
        return sorted(t.name for t in await self.mcp.list_tools() if t.name not in self.guarded)


def _verdict(decision: Decision) -> str:
    return "allowed" if decision.allow else f"denied: {decision.reason or 'no reason given'}"
