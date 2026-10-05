"""The documents server: on an in-memory store, then on the real Django store over real HTTP."""

import asyncio
import socket
import threading
import time
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
import uvicorn
from asgiref.sync import sync_to_async

from core.policy.engine import PolicyEngine
from core.policy.rules import ALLOW, FunctionRule
from core.types import Caller, Citation, DocumentHit, DocumentText, ToolCall
from mcp_servers.documents.tools import PART_CHARS, create_server
from providers.mcp.client import McpToolClient

SECRET = "s3cret"
LABELS = {"teller": ["public", "internal"], "auditor": ["public", "internal", "medical"]}
ENGINE = PolicyEngine(
    [
        FunctionRule("documents.search", lambda c, a, r: ALLOW),
        FunctionRule("documents.get", lambda c, a, r: ALLOW),
    ]
)
KYC = uuid4()
MEDICAL = uuid4()
LONG = uuid4()


class MemoryStore:
    """A DocumentStore over three documents, filtered by label like the real one."""

    docs = {
        KYC: DocumentText(KYC, "KYC Policy", "internal", "Both holders must provide ID."),
        MEDICAL: DocumentText(MEDICAL, "Medical", "medical", "Report."),
        LONG: DocumentText(LONG, "Handbook", "public", "x" * (PART_CHARS + 10)),
    }

    def __init__(self) -> None:
        self.searches: list[tuple[str, list[str], int, str | None]] = []

    async def search(self, query, classifications, limit, doc_type=None):
        self.searches.append((query, classifications, limit, doc_type))
        return [
            DocumentHit(d.document_id, d.title, "4.2", d.text, 0.5, d.classification)
            for d in self.docs.values()
            if d.classification in classifications and query.lower() in d.text.lower()
        ][:limit]

    async def get_document(self, document_id: UUID, classifications: list[str]) -> DocumentText:
        doc = self.docs[document_id]
        if doc.classification not in classifications:
            raise KeyError(str(document_id))
        return doc


def teller() -> Caller:
    return Caller("S1", "teller", "staff", {})


@asynccontextmanager
async def documents(store=None):
    server = create_server(store or MemoryStore(), ENGINE, SECRET, lambda role: LABELS[role])
    async with McpToolClient({"documents": server.mcp}, SECRET) as client:
        yield client


async def test_search_is_limited_to_the_callers_labels_and_cites_sections() -> None:
    store = MemoryStore()
    async with documents(store) as client:
        result = await client.call(
            teller(), ToolCall("1", "documents.search", {"query": "holders"})
        )
    assert result.ok
    assert result.data[0]["title"] == "KYC Policy"
    assert result.citations == (Citation("document", "KYC Policy", "4.2"),)
    assert store.searches == [("holders", ["public", "internal"], 4, None)]


async def test_search_limit_is_capped_and_doc_type_passed_on() -> None:
    store = MemoryStore()
    async with documents(store) as client:
        args = {"query": "x", "limit": 50, "doc_type": "circular"}
        await client.call(teller(), ToolCall("1", "documents.search", args))
    assert store.searches[0][2:] == (8, "circular")


async def test_get_returns_the_document_or_not_found() -> None:
    async with documents() as client:
        found = await client.call(
            teller(), ToolCall("1", "documents.get", {"document_id": str(KYC)})
        )
        hidden = await client.call(
            teller(), ToolCall("2", "documents.get", {"document_id": str(MEDICAL)})
        )
        junk = await client.call(teller(), ToolCall("3", "documents.get", {"document_id": "nope"}))
    assert found.data["text"] == "Both holders must provide ID."
    assert found.citations == (Citation("document", "KYC Policy", "whole document"),)
    assert hidden.error == "not_found"  # a document you may not read looks like no document
    assert junk.error == "not_found"


async def test_long_documents_come_in_parts() -> None:
    async with documents() as client:

        async def part(n: int | None = None):
            arguments = {"document_id": str(LONG)} | ({"part": n} if n else {})
            return await client.call(teller(), ToolCall("1", "documents.get", arguments))

        first, second, beyond = await part(), await part(2), await part(3)
    assert len(first.data["text"]) == PART_CHARS
    assert (first.data["part"], first.data["parts"]) == (1, 2)
    assert second.data["text"] == "x" * 10  # the rest
    assert beyond.error == "invalid_arguments"


async def test_every_documents_tool_is_guarded() -> None:
    server = create_server(MemoryStore(), ENGINE, SECRET, lambda role: LABELS[role])
    assert await server.tool_names() == ["documents.get", "documents.search"]
    assert await server.unguarded_tools() == []


# --- on the real Django store, over real HTTP ------------------------------------------------


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until(ready, timeout: float = 10.0) -> None:
    """Poll `ready()` from a worker thread; the server starts in a thread of its own."""
    deadline = time.monotonic() + timeout
    while not ready():
        if time.monotonic() > deadline:
            raise TimeoutError("server did not start")
        time.sleep(0.05)


@asynccontextmanager
async def running_over_http(server):
    """Serve the documents server on a local port with uvicorn, as it runs when deployed."""
    port = free_port()
    app = server.mcp.streamable_http_app(stateless_http=True, json_response=True)
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    await asyncio.to_thread(wait_until, lambda: uv.started)
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        uv.should_exit = True
        thread.join(timeout=5)


@pytest.mark.django_db(transaction=True)
async def test_search_over_http_on_the_django_store() -> None:
    from apps.knowledge.adapters import DjangoDocumentStore
    from apps.knowledge.tests.factories import indexed_document, vector

    await sync_to_async(indexed_document)(
        "KYC Policy", [("4.2 Joint accounts", "Both holders must provide ID.", vector(0))]
    )
    await sync_to_async(indexed_document)(
        "Medical guide",
        [("1 Reports", "Holders of medical reports.", vector(0))],
        classification="medical",
    )

    class Embedder:
        async def embed(self, texts):
            return [vector(0) for _ in texts]

    server = create_server(DjangoDocumentStore(Embedder()), ENGINE, SECRET, lambda r: LABELS[r])
    async with (
        running_over_http(server) as url,
        McpToolClient({"documents": url}, SECRET) as client,
    ):
        result = await client.call(
            teller(), ToolCall("1", "documents.search", {"query": "holders"})
        )

    assert result.ok
    assert [h["title"] for h in result.data] == ["KYC Policy"]  # the medical guide stays hidden
    assert result.citations == (Citation("document", "KYC Policy", "4.2 Joint accounts"),)
