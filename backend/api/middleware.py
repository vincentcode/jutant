"""Database connection cleanup and request ids, as plain ASGI middleware.

Django closes stale database connections through its own request signals, which FastAPI does
not fire, so this does it around every request. Both wrap the whole response, including a
streamed one, so cleanup happens after the last event is sent, not when the route returns.
"""

import uuid

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"


class DbConnectionMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        await sync_to_async(close_old_connections)()
        try:
            await self.app(scope, receive, send)
        finally:
            await sync_to_async(close_old_connections)()


class RequestIdMiddleware:
    """Gives every request an id (or keeps the caller's), returned in the X-Request-Id header."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        request_id = headers.get(REQUEST_ID_HEADER.encode(), b"").decode() or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = [
                    *message["headers"],
                    (REQUEST_ID_HEADER.encode(), request_id.encode()),
                ]
            await send(message)

        await self.app(scope, receive, send_with_id)
