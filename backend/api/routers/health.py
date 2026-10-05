"""Whether the database, the model and each MCP server answer. Open to monitoring, no login."""

from asgiref.sync import sync_to_async
from django.db import connection
from fastapi import APIRouter, Depends, Response, status

from api.deps import get_runtime
from api.schemas import HealthOut
from config.container import Runtime

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(response: Response, runtime: Runtime = Depends(get_runtime)) -> HealthOut:
    ping_model = getattr(runtime.orchestrator.model, "ping", None)
    result = HealthOut(
        database=await sync_to_async(_database_ok)(),
        model=bool(await ping_model()) if ping_model else True,
        mcp_servers=await runtime.tool_client.ping(),
    )
    if not (result.database and result.model and all(result.mcp_servers.values())):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


def _database_ok() -> bool:
    try:
        connection.ensure_connection()
    except Exception:
        return False
    return True
