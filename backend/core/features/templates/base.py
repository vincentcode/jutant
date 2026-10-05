"""What every feature template implements, and the context a template runs with.

A template is the behaviour behind a feature (answer from documents, look up a record, run a
playbook...). A pack turns a template into a feature by giving it a prompt and a list of tools.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from core.errors import InvalidToolCall, UnknownTool
from core.events import Event, Failed, TextDelta, ToolFinished, ToolStarted
from core.ports import AuditSink, ModelProvider, PlaybookStore
from core.types import Caller, Feature, Message, ToolResult

if TYPE_CHECKING:
    from core.playbooks.runner import PlaybookRunner
    from core.tools.gateway import ToolGateway

# Reasons a template can fail with; the client turns these into plain-language messages.
STEP_LIMIT = "step_limit"
TOOL_FAILED = "tool_failed"
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


class FeatureTemplate(Protocol):
    id: str
    requires_citation: bool

    def run(self, ctx: FeatureContext) -> AsyncIterator[Event]: ...


async def tool_loop(ctx: FeatureContext) -> AsyncIterator[Event]:
    """Model, tool calls, model again, until the model answers in text.

    The model sees only the routed feature's tools. Every call goes through the gateway. A failed
    call is returned to the model once so it can correct itself; a second failure ends the turn.
    The loop stops after `max_steps` model calls.
    """
    messages = list(ctx.messages)
    tools = ctx.gateway.catalog.specs_for(ctx.feature.tools)
    failures = 0
    for _ in range(ctx.max_steps):
        reply = await ctx.model.chat(messages, tools)
        if not reply.tool_calls:
            yield TextDelta((reply.text or "").strip())
            return
        messages.append(Message("assistant", reply.text or "", tool_calls=reply.tool_calls))
        for call in reply.tool_calls:
            yield ToolStarted(call)
            try:
                result = await ctx.gateway.execute(
                    ctx.caller, ctx.feature, call, str(ctx.conversation_id)
                )
            except (InvalidToolCall, UnknownTool) as exc:
                result = ToolResult(
                    call.id, ok=False, data={"problems": [str(exc)]}, error="invalid_arguments"
                )
            ctx.results.append(result)
            yield ToolFinished(result)
            messages.append(Message("tool", tool_message(result), tool_call_id=call.id))
            if not result.ok:
                failures += 1
        if failures >= MAX_TOOL_FAILURES:
            yield Failed(TOOL_FAILED)
            return
    yield Failed(STEP_LIMIT)


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
