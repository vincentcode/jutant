"""create_app(): routers, middleware, lifespan, admin mount.

Run: uvicorn api.main:create_app --factory
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from django.conf import settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config.bootstrap  # noqa: F401  (sets up Django before any model is imported)
from api.errors import register_error_handlers
from api.middleware import DbConnectionMiddleware, RequestIdMiddleware
from api.routers import auth, conversations, documents, features, health
from config.asgi import application as django_app


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the orchestrator once, open MCP sessions, check the pack contract; close on exit."""
    from config.container import build_orchestrator

    app.state.orchestrator = build_orchestrator()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Jutant", lifespan=lifespan)
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
    for module in (auth, conversations, features, documents, health):
        app.include_router(module.router, prefix="/api")
    app.mount("/admin", django_app)
    return app
