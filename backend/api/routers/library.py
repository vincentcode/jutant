"""The Knowledge panel: the documents the caller's role may read, to browse and summarise."""

from fastapi import APIRouter, Depends, Query

from api.deps import get_caller, get_runtime
from api.schemas import DocumentOut
from config.container import Runtime
from core.types import Caller

router = APIRouter(prefix="/documents", tags=["knowledge"])


@router.get("")
async def list_documents(
    q: str = Query("", max_length=100, description="words in the title"),
    doc_type: str = Query("", max_length=64, alias="type"),
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> list[DocumentOut]:
    """Indexed documents with a label the caller's role may read, newest first. Titles and
    types only: reading one goes through the assistant, which checks access again."""
    entries = await runtime.library.list(
        runtime.pack.readable_classifications(caller.role), q.strip(), doc_type.strip()
    )
    return [DocumentOut(**vars(e)) for e in entries]
