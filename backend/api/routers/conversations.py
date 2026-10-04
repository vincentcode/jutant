"""Conversations. A conversation that does not belong to the caller returns 404, not 403."""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.deps import get_caller, get_orchestrator
from api.schemas import AskRequest, ConversationOut, MessageOut
from core.orchestrator.orchestrator import Orchestrator
from core.types import Caller

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", status_code=201)
async def start(caller: Caller = Depends(get_caller)) -> ConversationOut:
    raise NotImplementedError


@router.get("")
async def list_mine(caller: Caller = Depends(get_caller)) -> list[ConversationOut]:
    raise NotImplementedError


@router.get("/{conversation_id}/messages")
async def history(conversation_id: UUID, caller: Caller = Depends(get_caller)) -> list[MessageOut]:
    raise NotImplementedError


@router.post("/{conversation_id}/ask")
async def ask(
    conversation_id: UUID,
    body: AskRequest,
    caller: Caller = Depends(get_caller),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    """Server-sent event stream of the answer."""
    raise NotImplementedError
