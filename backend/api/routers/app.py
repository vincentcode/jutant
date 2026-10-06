"""The assistant's name and look, for the client, before anyone signs in."""

from django.conf import settings
from fastapi import APIRouter, Depends

from api.deps import get_runtime
from api.schemas import AppOut
from config.container import Runtime

router = APIRouter(prefix="/app", tags=["app"])


@router.get("")
async def app_info(runtime: Runtime = Depends(get_runtime)) -> AppOut:
    """Public: the sign-in page shows the name too. Nothing here is confidential."""
    return AppOut(
        name=runtime.pack.manifest.display_name,
        accent=settings.JUTANT_THEME_ACCENT or None,
    )
