"""The features the caller's role may use, shown as chips in the chat client."""

from fastapi import APIRouter, Depends

from api.deps import get_caller, get_orchestrator
from api.schemas import FeatureOut
from core.orchestrator.orchestrator import Orchestrator
from core.types import Caller

router = APIRouter(prefix="/features", tags=["features"])


@router.get("")
async def list_features(
    caller: Caller = Depends(get_caller),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> list[FeatureOut]:
    return [
        FeatureOut(id=f.id, template=f.template, title=f.title, description=f.description)
        for f in orchestrator.registry.for_role(caller.role)
    ]
