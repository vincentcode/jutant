"""Conversations and asking questions.

A conversation that does not belong to the caller answers 404, never 403, so its existence is
not revealed. Access to the chosen feature is checked before the answer starts streaming, so a
refusal is a plain 403 rather than an event mid-stream.
"""

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from api import sse
from api.deps import get_caller, get_runtime
from api.schemas import AskRequest, ConversationOut, MessageOut
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
    caller: Caller = Depends(get_caller), runtime: Runtime = Depends(get_runtime)
) -> list[ConversationOut]:
    return [ConversationOut(**asdict(c)) for c in await runtime.conversations.list_for(caller.id)]


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
            created_at=m.created_at,
        )
        for m in await runtime.conversations.history(conversation_id)
    ]


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
            caller, conversation_id, body.text, body.feature_id, upload_text
        )

    return StreamingResponse(
        sse.stream(request.app.state.queue, events),
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
