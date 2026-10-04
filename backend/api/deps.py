"""FastAPI dependencies: the caller and the orchestrator."""

from fastapi import Request

from core.orchestrator.orchestrator import Orchestrator
from core.types import Caller


async def get_caller(request: Request) -> Caller:
    """Read and verify the session cookie; 401 if missing or expired."""
    raise NotImplementedError


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator
