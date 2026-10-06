"""create_app(): routers, middleware, lifespan, admin mount.

Run: uvicorn api.main:create_app --factory
"""

import config.bootstrap  # noqa: F401, I001  (sets up Django before any model is imported)

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from django.conf import settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import register_error_handlers
from api.middleware import DbConnectionMiddleware, RequestIdMiddleware
from api.queue import GenerationQueue
from api.routers import app as app_info
from api.routers import auth, conversations, documents, features, health, home, library
from config.asgi import application as django_app
from config.container import Runtime, build_runtime


def create_app(runtime: Runtime | None = None) -> FastAPI:
    """The API. Pass a started `runtime` (tests do) to skip building and starting the real one."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if runtime is not None:
            yield
            return
        # Connect to the MCP servers, read their tools and check the pack; refuse to start if
        # the pack fails. Closed again on shutdown.
        real = build_runtime()
        await real.start()
        app.state.runtime = real
        try:
            yield
        finally:
            await real.stop()

    app = FastAPI(title="Jutant", lifespan=lifespan)
    app.state.runtime = runtime
    app.state.queue = GenerationQueue(settings.JUTANT_MAX_CONCURRENT_GENERATIONS)
    app.add_middleware(DbConnectionMiddleware)
    app.add_middleware(RequestIdMiddleware)
    if settings.JUTANT_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.JUTANT_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    register_error_handlers(app)
    for module in (app_info, auth, conversations, features, documents, health, home, library):
        app.include_router(module.router, prefix="/api")
    app.mount("/admin", django_app)
    return app
