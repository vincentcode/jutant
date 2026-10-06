"""The features the caller's role may use, shown as chips in the chat client."""

from fastapi import APIRouter, Depends

from api.deps import get_caller, get_orchestrator
from api.schemas import FeatureOut
from core.orchestrator.orchestrator import Orchestrator
from core.types import Caller

router = APIRouter(prefix="/features", tags=["features"])

# How the client groups features in its menu, by the kind of help (the template), so any pack
# is grouped without saying so.
GROUPS = {
    "record_lookup": "Look something up",
    "record_summary": "Look something up",
    "document_qa": "Policies and documents",
    "document_extraction": "Policies and documents",
    "checklist": "Policies and documents",
    "guided_playbook": "Step-by-step help",
}


@router.get("")
async def list_features(
    caller: Caller = Depends(get_caller),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> list[FeatureOut]:
    return [
        FeatureOut(
            id=f.id,
            template=f.template,
            title=f.title,
            description=f.description,
            group=GROUPS.get(f.template, ""),
            examples=list(f.suggestions[:2]),
        )
        for f in orchestrator.registry.for_role(caller.role)
    ]
