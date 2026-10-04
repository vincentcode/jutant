from fastapi import APIRouter

from api.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> HealthOut:
    """Database, model and MCP server status."""
    raise NotImplementedError
