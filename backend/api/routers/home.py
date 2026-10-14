"""The home screen: starting points from every pack, those the caller may use, mixed."""

from fastapi import APIRouter, Depends

from api.deps import get_caller, get_runtime
from api.schemas import HomeCardOut, HomeOut
from config.container import Runtime
from core.types import Caller

router = APIRouter(prefix="/home", tags=["home"])


@router.get("")
async def home(
    caller: Caller = Depends(get_caller), runtime: Runtime = Depends(get_runtime)
) -> HomeOut:
    allowed = {f.id for f in runtime.orchestrator.registry.for_caller(caller)}
    return HomeOut(
        cards=[
            HomeCardOut(
                title=c.title,
                description=c.description,
                feature_id=c.feature,
                icon=c.icon,
                label=c.label,
            )
            for c in runtime.deployment.home_cards
            if c.feature in allowed
        ],
    )
