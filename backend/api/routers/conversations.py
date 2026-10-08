"""Conversations and asking questions.

A conversation that does not belong to the caller answers 404, never 403, so its existence is
not revealed. Access to the chosen feature is checked before the answer starts streaming, so a
refusal is a plain 403 rather than an event mid-stream.
"""

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from api import sse
from api.deps import get_caller, get_runtime
from api.schemas import (
    AskRequest,
    ConversationOut,
    ConversationRename,
    FeedbackIn,
    FeedbackOut,
    MessageOut,
    ProcedureOut,
    SubjectOut,
)
from api.sse import step_out
from apps.conversation.adapters import Rating
from config.container import Runtime
from core.types import Caller

router = APIRouter(prefix="/conversations", tags=["conversations"])

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")


@router.post("", status_code=status.HTTP_201_CREATED)
async def start(
    caller: Caller = Depends(get_caller), runtime: Runtime = Depends(get_runtime)
) -> ConversationOut:
    conversation_id = await runtime.conversations.create(caller)
    summary = await runtime.conversations.owned(conversation_id, caller.id)
    return ConversationOut(**asdict(summary))


@router.get("")
async def list_mine(
    q: str = Query("", max_length=100, description="words in the title or the messages"),
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> list[ConversationOut]:
    found = await runtime.conversations.list_for(caller.id, search=q.strip())
    return [ConversationOut(**asdict(c)) for c in found]


@router.patch("/{conversation_id}")
async def rename(
    conversation_id: UUID,
    body: ConversationRename,
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> ConversationOut:
    renamed = await runtime.conversations.rename(conversation_id, caller.id, body.title.strip())
    if renamed is None:
        raise NOT_FOUND
    return ConversationOut(**asdict(renamed))


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    conversation_id: UUID,
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> None:
    """Delete the conversation with its messages, uploads and ratings. The audit log keeps
    what happened in it."""
    if not await runtime.conversations.delete(conversation_id, caller.id):
        raise NOT_FOUND
    await runtime.orchestrator.audit.record(
        caller, "conversation_deleted", {"conversation_id": str(conversation_id)}
    )


@router.get("/{conversation_id}/subjects")
async def subjects(
    conversation_id: UUID,
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> list[SubjectOut]:
    """The subjects open in the conversation, current first, for staff to return to."""
    await _owned(runtime, conversation_id, caller)
    open_ = await runtime.orchestrator.subjects(conversation_id)
    return [
        SubjectOut(id=id_, title=title, procedure=procedure, current=index == 0)
        for index, (id_, title, procedure) in enumerate(open_)
    ]


@router.get("/{conversation_id}/procedure")
async def procedure(
    conversation_id: UUID,
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> ProcedureOut | None:
    """The procedure in progress and the step it waits on (paused while staff ask other
    things), or null."""
    await _owned(runtime, conversation_id, caller)
    orchestrator = runtime.orchestrator
    run = await orchestrator.playbooks.get_run(conversation_id)
    current = await orchestrator.runner.current(conversation_id)
    if run is None or current is None:
        return None
    title, step = current
    return ProcedureOut(
        playbook_id=run.playbook_id,
        playbook_title=title,
        step_order=step.order,
        step_title=step.title,
        paused=run.paused,
    )


@router.get("/{conversation_id}/messages")
async def history(
    conversation_id: UUID,
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> list[MessageOut]:
    await _owned(runtime, conversation_id, caller)
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            feature_id=m.feature_id,
            citations=[asdict(c) for c in m.citations],
            steps=[step_out(s) for s in m.steps],
            feedback=_feedback_out(m.feedback) if m.feedback else None,
            created_at=m.created_at,
        )
        for m in await runtime.conversations.history(conversation_id, caller.id)
    ]


@router.put("/{conversation_id}/messages/{message_id}/feedback")
async def give_feedback(
    conversation_id: UUID,
    message_id: UUID,
    body: FeedbackIn,
    background: BackgroundTasks,
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> FeedbackOut:
    """Rate an answer, or change the rating. It is stored, audited, and attached to the
    answer's trace (after the response, so a slow tracing backend never delays staff)."""
    await _owned(runtime, conversation_id, caller)
    rated = await runtime.conversations.rate(
        conversation_id, message_id, caller, body.rating, body.reason or "", body.comment
    )
    if rated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "answer not found")
    await runtime.orchestrator.audit.record(
        caller,
        "feedback_given",
        {
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "feature_id": rated.feature_id,
            "rating": body.rating,
            "reason": body.reason,
            "comment": body.comment,
        },
    )
    background.add_task(
        runtime.feedback.send,
        rated.trace_context,
        staff_id=caller.id,
        rating=body.rating,
        reason=body.reason or "",
        comment=body.comment,
        feature_id=rated.feature_id,
    )
    return _feedback_out(rated.rating)


def _feedback_out(rating: Rating) -> FeedbackOut:
    return FeedbackOut(rating=rating.rating, reason=rating.reason or None, comment=rating.comment)


@router.post(
    "/{conversation_id}/ask",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Server-sent events"}},
)
async def ask(
    conversation_id: UUID,
    body: AskRequest,
    request: Request,
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> StreamingResponse:
    """Ask a question; the answer streams back as server-sent events."""
    await _owned(runtime, conversation_id, caller)
    _check_feature(runtime, caller, body.feature_id)
    upload_text = None
    if body.upload_id is not None:
        upload_text = await runtime.conversations.upload_text(body.upload_id, conversation_id)
        if upload_text is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "upload not found")

    def events():
        return runtime.orchestrator.ask(
            caller,
            conversation_id,
            body.text,
            body.feature_id,
            upload_text,
            preferred_feature_id=body.preferred_feature_id,
            reply_as=body.reply_as,
            subject_id=body.subject_id,
            picked=body.picked,
        )

    return StreamingResponse(
        sse.stream(request.app.state.queue, events, labels=runtime.pack.manifest.tool_labels),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _owned(runtime: Runtime, conversation_id: UUID, caller: Caller) -> None:
    if await runtime.conversations.owned(conversation_id, caller.id) is None:
        raise NOT_FOUND


def _check_feature(runtime: Runtime, caller: Caller, feature_id: str | None) -> None:
    registry = runtime.orchestrator.registry
    if feature_id is None:
        if not registry.for_role(caller.role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "no features for your role")
        return
    try:
        feature = registry.get(feature_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown feature") from None
    if not feature.allows(caller.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "your role may not use this feature")
