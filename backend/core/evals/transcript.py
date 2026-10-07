"""Replays a conversation through the orchestrator and records what happened at each message,
for a person to read and grade: which feature answered and how routing decided, the tools
called, the answer and its sources, any failure, and the procedure's state afterwards.

Used for held-out evaluation, where answers are judged by meaning, not by fixed checks. It
only observes: the orchestrator runs exactly as deployed, its audit records passed through.
"""

import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from core.errors import PolicyDenied
from core.events import (
    Completed,
    Failed,
    FeatureSelected,
    PlaybookStepShown,
    ReplyUnclear,
    ToolFinished,
    ToolStarted,
)
from core.ports import AuditSink
from core.types import Caller

if TYPE_CHECKING:
    from core.orchestrator.orchestrator import Orchestrator


@dataclass
class Turn:
    message: str
    feature: str | None = None
    routed_by: str | None = None  # pattern, meaning, model, preferred... or "procedure"
    switched_from: str | None = None
    reply_read_as: str | None = None  # during a procedure: answer, about_step, new_question...
    tools: list[dict[str, Any]] = field(default_factory=list)  # name, arguments, ok, error
    steps: list[str] = field(default_factory=list)  # procedure steps shown
    answer: str = ""
    sources: list[str] = field(default_factory=list)
    failed: str | None = None
    procedure: str | None = None  # afterwards: "Blocked card · step 2 (paused)", or None
    seconds: float = 0.0


@dataclass
class Transcript:
    item_id: str
    role: str
    branch: str
    attempt: int
    turns: list[Turn] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class _Listening:
    """Passes audit records on, keeping what routing and procedure turns decided."""

    def __init__(self, inner: AuditSink):
        self.inner = inner
        self.seen: list[tuple[str, dict[str, Any]]] = []

    async def record(self, caller: Caller, event: str, detail: dict[str, Any]) -> None:
        self.seen.append((event, detail))
        await self.inner.record(caller, event, detail)


async def replay(
    orchestrator: "Orchestrator",
    caller: Caller,
    messages: list[str],
    item_id: str,
    attempt: int = 1,
) -> Transcript:
    """Ask `messages` in order in one new conversation, as `caller`."""
    listening = _Listening(orchestrator.audit)
    orchestrator.audit = listening  # type: ignore[assignment]
    try:
        conversation_id = await orchestrator.conversations.create(caller)
        transcript = Transcript(
            item_id, caller.role, str(caller.attributes.get("branch", "")), attempt
        )
        for message in messages:
            listening.seen.clear()
            turn = Turn(message)
            started = time.perf_counter()
            try:
                async for event in orchestrator.ask(caller, conversation_id, message):
                    _note(turn, event)
            except PolicyDenied as denied:
                turn.failed = f"denied: {denied}"
            turn.seconds = round(time.perf_counter() - started, 1)
            for name, detail in listening.seen:
                if name == "feature_routed":
                    turn.routed_by = str(detail.get("chosen_by"))
                elif name == "turn_read":
                    turn.reply_read_as = f"{detail.get('action')} (by {detail.get('by')})"
            if turn.feature is None and turn.failed is None and (turn.steps or turn.answer):
                turn.routed_by = "procedure"
            turn.procedure = await _procedure(orchestrator, conversation_id)
            transcript.turns.append(turn)
        return transcript
    finally:
        orchestrator.audit = listening.inner  # type: ignore[assignment]


def _note(turn: Turn, event: object) -> None:
    match event:
        case FeatureSelected(feature_id, switched_from):
            turn.feature, turn.switched_from = feature_id, switched_from
        case ToolStarted(call):
            turn.tools.append({"name": call.name, "arguments": dict(call.arguments)})
        case ToolFinished(result):
            if turn.tools:
                turn.tools[-1].update(ok=result.ok, error=result.error)
        case PlaybookStepShown(_, step, title, answered):
            label = f"{title} · step {step.order}: {step.title}"
            turn.steps.append(f"{label} (answered: {answered})" if answered else label)
        case ReplyUnclear(order, title):
            turn.reply_read_as = f"unclear (asked: answer to step {order} {title}, or question?)"
        case Completed(answer):
            turn.answer = answer.text
            turn.sources = [f"{c.title}, {c.locator}" for c in answer.citations]
        case Failed(reason):
            turn.failed = reason


async def _procedure(orchestrator: "Orchestrator", conversation_id: Any) -> str | None:
    run = await orchestrator.playbooks.get_run(conversation_id)
    current = await orchestrator.runner.current(conversation_id)
    if run is None or current is None:
        return None
    title, step = current
    return f"{title} · step {step.order} ({step.title}){' · paused' if run.paused else ''}"
