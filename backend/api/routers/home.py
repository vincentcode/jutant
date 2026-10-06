"""The home screen: starting points and quick actions from the pack, for the caller's role."""

from fastapi import APIRouter, Depends

from api.deps import get_caller, get_runtime
from api.schemas import HomeCardOut, HomeOut, QuickActionOut
from config.container import Runtime
from core.types import Caller

router = APIRouter(prefix="/home", tags=["home"])


@router.get("")
async def home(
    caller: Caller = Depends(get_caller), runtime: Runtime = Depends(get_runtime)
) -> HomeOut:
    allowed = {f.id for f in runtime.orchestrator.registry.for_role(caller.role)}
    home = runtime.pack.manifest.home
    return HomeOut(
        cards=[
            HomeCardOut(
                title=c.title,
                description=c.description,
                feature_id=c.feature,
                icon=c.icon,
                label=c.label,
            )
            for c in home.cards
            if c.feature in allowed
        ],
        quick_actions=[
            QuickActionOut(label=a.label, feature_id=a.feature)
            for a in home.quick_actions
            if a.feature in allowed
        ],
    )
