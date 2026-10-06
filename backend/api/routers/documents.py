"""Uploading a file into a conversation, for the extraction feature.

The file's text is read here (with OCR for photos and scans) and kept with the conversation;
it is never added to the search index. The returned upload id is passed to `ask`.
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from api.deps import get_caller, get_runtime
from api.routers.conversations import NOT_FOUND
from api.schemas import UploadOut
from config.container import Runtime
from core.types import Caller
from ingestion.uploads import MAX_UPLOAD_BYTES, UploadError, read_upload

router = APIRouter(prefix="/conversations", tags=["documents"])


@router.post("/{conversation_id}/upload", status_code=status.HTTP_201_CREATED)
async def upload(
    conversation_id: UUID,
    file: UploadFile,
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> UploadOut:
    if await runtime.conversations.owned(conversation_id, caller.id) is None:
        raise NOT_FOUND
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file is too large")
    filename = file.filename or "upload"
    try:
        read = await asyncio.to_thread(read_upload, filename, data, runtime.ocr)
    except UploadError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    upload_id = await runtime.conversations.add_upload(
        conversation_id, filename, file.content_type or "", read.text
    )
    await runtime.orchestrator.audit.record(
        caller,
        "document_uploaded",
        {
            "conversation_id": str(conversation_id),
            "filename": filename,
            "characters": len(read.text),
        },
    )
    return UploadOut(
        upload_id=upload_id, filename=filename, characters=len(read.text), note=read.note
    )
