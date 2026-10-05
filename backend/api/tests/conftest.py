"""The API wired exactly as deployed, except for a scripted model, a fake OCR engine and the
MCP servers running in-process (the banking pack on its fake bank, and the documents server)."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings

from api.main import create_app
from apps.identity.tests.factories import PASSWORD, StaffFactory
from apps.knowledge.adapters import DjangoDocumentStore
from config.container import Runtime, build_runtime
from core.packs.loader import load_pack
from core.policy.engine import PolicyEngine
from core.types import ModelReply
from mcp_servers.documents.tools import create_server as documents_server
from packs.banking.mcp_servers import build_servers
from providers.llm.fake import FakeModel


class FakeOcr:
    def extract_text(self, file_bytes: bytes, mime_type: str) -> str:
        return "REPUBLIC OF GHANA\nName: AMA MENSAH\nID: GHA-123456789-0"


@dataclass
class Api:
    http: httpx.AsyncClient
    runtime: Runtime
    model: FakeModel

    async def login(self, username: str, password: str = PASSWORD) -> httpx.Response:
        return await self.http.post(
            "/api/auth/login", json={"username": username, "password": password}
        )

    async def conversation(self) -> str:
        response = await self.http.post("/api/conversations")
        assert response.status_code == 201, response.text
        return response.json()["id"]

    async def ask(self, conversation_id: str, **body: Any) -> list[tuple[str, Any]]:
        """POST ask and return the (event, data) pairs of the stream."""
        async with self.http.stream(
            "POST", f"/api/conversations/{conversation_id}/ask", json=body
        ) as response:
            assert response.status_code == 200, await response.aread()
            assert response.headers["content-type"].startswith("text/event-stream")
            return parse_sse((await response.aread()).decode())


def parse_sse(text: str) -> list[tuple[str, Any]]:
    events = []
    for block in text.split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        name = next((ln[6:].strip() for ln in lines if ln.startswith("event:")), None)
        data = "\n".join(ln[5:].strip() for ln in lines if ln.startswith("data:"))
        if name:
            events.append((name, json.loads(data)))
    return events


def make_staff(username: str, role: str = "teller", branch: str = "ACC-01", **kwargs):
    return sync_to_async(StaffFactory)(
        user__username=username, role=role, attributes={"branch": branch}, **kwargs
    )


@asynccontextmanager
async def api(*replies: ModelReply) -> AsyncIterator[Api]:
    """A started API on the scripted `replies`. Opened inside each test, because the MCP
    sessions must close in the task that opened them."""
    pack = load_pack(settings.JUTANT_PACK_PATH)
    engine = PolicyEngine(pack.rules, pack.field_rules)
    secret = settings.JUTANT_CALLER_SECRET
    servers = {
        "documents": documents_server(
            DjangoDocumentStore(None), engine, secret, pack.readable_classifications
        ).mcp,
        **{name: s.mcp for name, s in build_servers(engine, secret, "fake").items()},
    }
    model = FakeModel(replies=list(replies))
    runtime = build_runtime(model=model, servers=servers, ocr=FakeOcr())
    await runtime.start()
    try:
        app = create_app(runtime)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            yield Api(http, runtime, model)
    finally:
        await runtime.stop()
