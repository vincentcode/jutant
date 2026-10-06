"""What every feature template implements, and the context a template runs with.

A template is the behaviour behind a feature (answer from documents, look up a record, run a
playbook...). A pack turns a template into a feature by giving it a prompt and a list of tools.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from core.errors import InvalidToolCall, ModelUnavailable, UnknownTool
from core.events import Event, Failed, TextDelta, ToolFinished, ToolStarted
from core.features.prefetch import planned_calls
from core.observability import Trace
from core.ports import AuditSink, ModelProvider, PlaybookStore
from core.types import Caller, Feature, Message, ModelReply, ToolCall, ToolResult, ToolSpec

if TYPE_CHECKING:
    from core.playbooks.runner import PlaybookRunner
    from core.tools.gateway import ToolGateway

# Reasons a template can fail with; the client turns these into plain-language messages.
STEP_LIMIT = "step_limit"
TOOL_FAILED = "tool_failed"
DENIED = "denied"
MAX_TOOL_FAILURES = 2  # one failure is shown to the model so it can correct itself


@dataclass
class FeatureContext:
    caller: Caller
    conversation_id: UUID
    feature: Feature
    question: str
    messages: list[Message]  # the prompt window: system, recent history, the question
    model: ModelProvider
    gateway: "ToolGateway"
    playbooks: PlaybookStore
    runner: "PlaybookRunner"
    audit: AuditSink
    max_steps: int
    upload_text: str | None = None  # text of a file uploaded for extraction, already OCR'd
    extraction_schemas: dict[str, list[str]] = field(default_factory=dict)
    results: list[ToolResult] = field(default_factory=list)  # filled by the tool loop
    trace: Trace = field(default_factory=Trace)  # the turn's span, for tool call spans
    # What prefetch calls and searches read: the question, and for a follow-up the previous one.
    lookup_text: str = ""

    @property
    def lookup(self) -> str:
        return self.lookup_text or self.question


class FeatureTemplate(Protocol):
    id: str
    requires_citation: bool

    def run(self, ctx: FeatureContext) -> AsyncIterator[Event]: ...


async def tool_loop(ctx: FeatureContext) -> AsyncIterator[Event]:
    """Model, tool calls, model again, until the model answers in text.

    The feature's prefetch calls whose arguments the question supplies are made first, in
    code, and the model starts with their results. The model sees only the routed feature's
    tools. Every call goes through the gateway. A failed call of the model's is returned to it
    once so it can correct itself; a second failure ends the turn. The loop stops after
    `max_steps` model calls.

    A small model sometimes answers from memory (inventing a source) or replies with nothing,
    without looking anything up. If its first reply calls no tool although the feature has
    tools and nothing was prefetched, that reply is dropped and the question is asked once more
    with an instruction to use the tools. Keeping the made-up answer in view makes the model
    repeat it.

    Replies are streamed, except one that may still be dropped that way.

    A call the policy refuses ends the turn at once, as `denied`: the model cannot change who
    the caller is, and asking it to write about the refusal would only keep staff waiting.
    """
    messages = list(ctx.messages)
    tools = ctx.gateway.catalog.specs_for(ctx.feature.tools)
    for call in planned_calls(ctx.feature, ctx.lookup):
        messages.append(Message("assistant", "", tool_calls=(call,)))
        async for event in run_call(ctx, call):
            yield event
        if ctx.results[-1].error == DENIED:
            yield Failed(DENIED)
            return
        messages.append(Message("tool", tool_message(ctx.results[-1]), tool_call_id=call.id))

    failures = 0
    nudged = False
    for _ in range(ctx.max_steps):
        may_nudge = bool(tools) and not ctx.results and not nudged
        if may_nudge:
            reply = await ctx.model.chat(messages, tools)
            streamed = False
        else:
            reply, streamed = None, False
            async for part in ctx.model.stream_chat(messages, tools):
                if isinstance(part, ModelReply):
                    reply = part
                else:
                    yield TextDelta(part, continues=streamed)
                    streamed = True
            if reply is None:
                raise ModelUnavailable("the model's reply ended without a result")
        if not reply.tool_calls:
            if may_nudge:
                nudged = True
                question = messages[-1]  # no tool messages yet, so the question is last
                messages[-1] = Message("user", f"{question.content}\n\n{use_tools_nudge(tools)}")
                continue
            if not streamed:
                yield TextDelta((reply.text or "").strip())
            return
        messages.append(Message("assistant", reply.text or "", tool_calls=reply.tool_calls))
        for call in reply.tool_calls:
            async for event in run_call(ctx, call):
                yield event
            result = ctx.results[-1]
            if result.error == DENIED:
                yield Failed(DENIED)
                return
            messages.append(Message("tool", tool_message(result), tool_call_id=call.id))
            if not result.ok:
                failures += 1
        if failures >= MAX_TOOL_FAILURES:
            yield Failed(TOOL_FAILED)
            return
    yield Failed(STEP_LIMIT)


async def run_call(ctx: FeatureContext, call: ToolCall) -> AsyncIterator[Event]:
    """Make one call through the gateway; its result is added to `ctx.results`."""
    yield ToolStarted(call)
    result = await call_tool(
        ctx.gateway, ctx.trace, ctx.caller, ctx.feature, str(ctx.conversation_id), call
    )
    ctx.results.append(result)
    yield ToolFinished(result)


async def call_tool(
    gateway: "ToolGateway",
    trace: Trace,
    caller: Caller,
    feature: Feature,
    conversation_id: str,
    call: ToolCall,
) -> ToolResult:
    """One tool call through the gateway (feature check, schema, policy, audit), as a span.
    A call the gateway rejects comes back as a failed result, not an exception."""
    attributes = {"tool.name": call.name, "tool.arguments": trace.masked(call.arguments)}
    with trace.span(call.name, "tool", **attributes) as span:
        try:
            result = await gateway.execute(caller, feature, call, conversation_id, span.carrier())
        except (InvalidToolCall, UnknownTool) as exc:
            result = ToolResult(
                call.id, ok=False, data={"problems": [str(exc)]}, error="invalid_arguments"
            )
        span.set(
            **{"tool.ok": result.ok, "tool.error": result.error},
            output=span.text(result.data),
            citations=len(result.citations),
        )
    return result


def use_tools_nudge(tools: list[ToolSpec]) -> str:
    names = ", ".join(t.name for t in tools)
    return (
        f"Do not answer from memory. First call one of your tools ({names}) to look this up, "
        "then answer only from what it returns."
    )


def tool_message(result: ToolResult) -> str:
    """The tool result as the model reads it: compact JSON, including any citations."""
    body: dict[str, Any] = {"ok": result.ok}
    if result.ok:
        body["data"] = result.data
        if result.citations:
            body["sources"] = [f"{c.title}, {c.locator}" for c in result.citations]
    else:
        body["error"] = result.error
        if result.data:
            body["detail"] = result.data
    return json.dumps(body, separators=(",", ":"), default=str)
