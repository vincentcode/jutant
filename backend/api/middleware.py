"""Database connection cleanup and request ids.

Django closes stale connections through its own request signals, which FastAPI does not fire.
"""

import uuid

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"


class DbConnectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        await sync_to_async(close_old_connections)()
        try:
            return await call_next(request)
        finally:
            await sync_to_async(close_old_connections)()


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
