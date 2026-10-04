"""Uploads for the extraction feature. Processed for that conversation only, never indexed."""

from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile

from api.deps import get_caller
from api.schemas import UploadOut
from core.types import Caller

router = APIRouter(prefix="/conversations", tags=["documents"])


@router.post("/{conversation_id}/upload")
async def upload(
    conversation_id: UUID, file: UploadFile, caller: Caller = Depends(get_caller)
) -> UploadOut:
    raise NotImplementedError
