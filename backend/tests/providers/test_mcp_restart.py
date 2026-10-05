"""An MCP server that stops and comes back, over real HTTP, as when its container restarts.

The client must survive the server going away (its failure used to tear down every session
and the task holding them), report calls during the outage as `upstream_error`, and reconnect
once the server is back.
"""

import asyncio
import threading

import uvicorn

from core.types import ToolCall
from mcp_servers.documents.tools import create_server
from providers.mcp.client import McpToolClient
from tests.mcp_servers.test_documents import (
    ENGINE,
    LABELS,
    SECRET,
    MemoryStore,
    free_port,
    teller,
    wait_until,
)

SEARCH = ToolCall("1", "documents.search", {"query": "holders"})


class Server:
    """The documents server on a fixed port, which can be stopped and started again."""

    def __init__(self, port: int):
        self.port = port
        self.url = f"http://127.0.0.1:{port}/mcp"
        self._uv: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    async def start(self) -> None:
        server = create_server(MemoryStore(), ENGINE, SECRET, lambda role: LABELS[role])
        app = server.mcp.streamable_http_app(stateless_http=True, json_response=True)
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self._uv = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._uv.run, daemon=True)
        self._thread.start()
        uv = self._uv
        await asyncio.to_thread(wait_until, lambda: uv.started)

    async def stop(self) -> None:
        assert self._uv is not None and self._thread is not None
        self._uv.should_exit = True
        await asyncio.to_thread(self._thread.join, 5)


async def test_the_client_survives_a_server_restart_and_reconnects() -> None:
    server = Server(free_port())
    await server.start()
    async with McpToolClient({"documents": server.url}, SECRET) as client:
        assert (await client.call(teller(), SEARCH)).ok

        await server.stop()
        down = await client.call(teller(), SEARCH)
        assert not down.ok and down.error == "upstream_error"  # a result, not a crash
        assert await client.ping() == {"documents": False}

        await server.start()
        assert await client.ping() == {"documents": True}  # reconnected
        assert (await client.call(teller(), SEARCH)).ok


async def test_a_call_after_a_restart_reconnects_without_a_health_check() -> None:
    server = Server(free_port())
    await server.start()
    async with McpToolClient({"documents": server.url}, SECRET) as client:
        assert (await client.call(teller(), SEARCH)).ok
        await server.stop()
        await server.start()
        results = [await client.call(teller(), SEARCH) for _ in range(2)]
        # At most the first call can fail, if the old connection was not yet seen to be gone.
        assert results[-1].ok
