"""Core errors -> HTTP responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.errors import InvalidToolCall, ModelUnavailable, PolicyDenied, UnknownTool

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PolicyDenied)
    async def denied(request: Request, exc: PolicyDenied) -> JSONResponse:
        return JSONResponse({"detail": "denied"}, status_code=403)

    @app.exception_handler(InvalidToolCall)
    @app.exception_handler(UnknownTool)
    async def tool_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Tool error", exc_info=exc)
        return JSONResponse({"detail": "internal_error"}, status_code=500)

    @app.exception_handler(ModelUnavailable)
    async def model_down(request: Request, exc: ModelUnavailable) -> JSONResponse:
        return JSONResponse({"detail": "model_unavailable"}, status_code=503)
