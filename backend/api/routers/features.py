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
    raise NotImplementedError
