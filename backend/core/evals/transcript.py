"""Replays a conversation through the orchestrator and records what happened at each message,
for a person to read and grade: which feature answered and how routing decided, the tools
called, the answer and its sources, any failure, and the procedure's state afterwards.

Used for held-out evaluation, where answers are judged by meaning, not by fixed checks. It
only observes: the orchestrator runs exactly as deployed, its audit records passed through.

A message may carry a label (`Label`): the feature that should answer it, or that the assistant
should ask what it is. When the assistant asks, the choice the label points to is picked (as
staff would), so the conversation goes on; with no label, or none that fits, nothing is picked.
Labels are scored by `core.evals.labels`.
"""

import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from core.errors import PolicyDenied
from core.events import (
    Choice,
    Clarify,
    Completed,
    Failed,
    FeatureSelected,
    PlaybookStepShown,
    ToolFinished,
    ToolStarted,
)
from core.ports import AuditSink
from core.types import Caller

if TYPE_CHECKING:
    from core.orchestrator.orchestrator import Orchestrator


HELDOUT_CALLER_ID = "heldout"  # who held-out runs ask as: left out of staff's own reports
ASK = "ask"  # a label: the assistant should ask what the message is


@dataclass(frozen=True)
class Label:
    """What should happen to a message. `expect`: the feature that should answer it, or "ask".
    `subject`: for a feature, whether it continues an open subject ("same") or starts one
    ("new"); unchecked if empty. `then`: for "ask", the feature staff would then pick."""

    expect: str
    subject: str = ""
    then: str = ""


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
    answered_by: str | None = None  # the feature whose answer it was (a procedure's too)
    read_as: str | None = None  # the reading's action: continue, return, new, stop
    asked: list[str] = field(default_factory=list)  # the picker's choices, if it asked
    ask_reason: str | None = None
    picked: str | None = None  # the choice picked for the label
    expect: str | None = None  # the label, if any
    expect_subject: str | None = None


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
    labels: list[Label | None] | None = None,
) -> Transcript:
    """Ask `messages` in order in one new conversation, as `caller`. `labels`: one per message
    (or None), saying what should happen to it."""
    listening = _Listening(orchestrator.audit)
    orchestrator.audit = listening  # type: ignore[assignment]
    try:
        conversation_id = await orchestrator.conversations.create(caller)
        transcript = Transcript(
            item_id, caller.role, str(caller.attributes.get("branch", "")), attempt
        )
        for index, message in enumerate(messages):
            label = labels[index] if labels and index < len(labels) else None
            listening.seen.clear()
            turn = Turn(message)
            if label is not None:
                turn.expect, turn.expect_subject = label.expect, label.subject or None
            started = time.perf_counter()
            try:
                choices: tuple[Choice, ...] = ()
                async for event in orchestrator.ask(caller, conversation_id, message):
                    _note(turn, event)
                    if isinstance(event, Clarify):
                        choices = event.choices
                picked = _pick(choices, label) if choices else None
                if picked is not None:
                    turn.picked = choices[picked].title
                    async for event in orchestrator.ask(
                        caller, conversation_id, message, **_said(choices[picked]), picked=picked
                    ):
                        _note(turn, event)
            except PolicyDenied as denied:
                turn.failed = f"denied: {denied}"
            turn.seconds = round(time.perf_counter() - started, 1)
            for name, detail in listening.seen:
                if name == "feature_routed":
                    turn.routed_by = str(detail.get("chosen_by"))
                elif name == "turn_read" and turn.read_as is None:  # the first reading
                    turn.read_as = str(detail.get("action"))
                    turn.reply_read_as = f"{detail.get('action')} (by {detail.get('by')})"
            if turn.feature is None and turn.failed is None and (turn.steps or turn.answer):
                turn.routed_by = "procedure"
            turn.procedure = await _procedure(orchestrator, conversation_id)
            transcript.turns.append(turn)
        return transcript
    finally:
        orchestrator.audit = listening.inner  # type: ignore[assignment]


def _pick(choices: tuple[Choice, ...], label: Label | None) -> int | None:
    """The choice staff would pick for `label`: the step's answer or the open subject with the
    expected feature (unless a new subject is expected), else that kind of help."""
    if label is None:
        return None
    wanted = label.then if label.expect == ASK else label.expect
    if not wanted:
        return None
    ranked = [
        lambda c: (
            c.kind in ("answer", "subject") and c.feature_id == wanted and label.subject != "new"
        ),
        lambda c: c.kind == "feature" and c.feature_id == wanted,
    ]
    for fits in ranked:
        for index, choice in enumerate(choices):
            if fits(choice):
                return index
    return None


def _said(choice: Choice) -> dict[str, Any]:
    """How the client sends a message again after staff picked `choice`."""
    match choice.kind:
        case "answer":
            return {"reply_as": "answer"}
        case "subject":
            return {"reply_as": "continue", "subject_id": choice.subject_id}
        case "resume":
            return {"reply_as": "resume"}
        case "feature":
            return {"feature_id": choice.feature_id, "reply_as": "question"}
    return {"reply_as": "question"}


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
        case Clarify(_, choices, reason):
            if not turn.asked:  # the first picker: a pick's answer does not ask again
                turn.asked, turn.ask_reason = [c.title for c in choices], reason
        case Completed(answer):
            turn.answer = answer.text
            turn.answered_by = answer.feature_id
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
