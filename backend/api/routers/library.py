"""The Knowledge panel: the documents the caller may read, in every pack they have a role in,
to browse and summarise."""

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
    seen: dict[str, DocumentOut] = {}
    for pack in runtime.deployment.names:
        acting = caller.in_pack(pack)
        if acting is None:
            continue
        readable = runtime.deployment.pack(pack).readable_classifications(acting.role)
        named = pack if len(runtime.deployment.packs) > 1 else ""
        for entry in await runtime.library.list(readable, q.strip(), doc_type.strip(), named):
            seen.setdefault(str(entry.id), DocumentOut(**vars(entry)))
    return sorted(seen.values(), key=lambda d: d.indexed_at, reverse=True)
