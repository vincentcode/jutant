"""McpToolClient: implements core.ports.ToolClient over the MCP SDK.

Holds one session per configured server, opened at start-up. Tool names are prefixed with the
server name (`documents.search`). On every call the caller is signed with a short-lived token
and sent in the request's `_meta`, never as a tool argument; the server verifies it before
running the tool. Results come back in the shared envelope (`core.tools.envelope`).

A server is given as a URL (streamable HTTP, as deployed) or as an in-process server object,
which tests and the pack contract check use to run the real tools without a network.

Each session runs in its own background task. When a server goes away (a restart, a crash),
the SDK's connection fails inside that task only: the session is marked closed, a call in
flight fails as `upstream_error`, and the next call or health check reconnects. Left to itself,
the failure would tear down every session and the task that opened them.
"""

import asyncio
import logging
from typing import Any

from mcp import Client
from mcp.server.mcpserver import MCPServer

from core.policy.identity import sign_caller
from core.tools import envelope
from core.types import Caller, ToolCall, ToolError, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

MAX_TOOL_PAGES = 20
CONNECT_TIMEOUT_S = 10.0


class ServerUnavailable(Exception):
    """A server could not be connected to."""


class _Session:
    """One server's session, owned by a background task so that its failure stays there."""

    def __init__(self, name: str, target: str | MCPServer, read_timeout_s: float):
        self.name = name
        self.target = target
        self.read_timeout_s = read_timeout_s
        self.client: Client | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()

    async def get(self) -> Client:
        """The open session, connecting first if there is none."""
        if self.client is not None:
            return self.client
        async with self._lock:  # one reconnect at a time
            if self.client is None:
                await self._open()
            assert self.client is not None
            return self.client

    async def close(self) -> None:
        self._stop.set()
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        self.client = None

    async def reset(self) -> None:
        """Drop the session, so the next call opens a new one."""
        async with self._lock:
            await self.close()

    async def _open(self) -> None:
        self._stop = asyncio.Event()
        ready = asyncio.Event()
        failure: list[BaseException] = []

        async def own() -> None:
            # The session is entered and left in this task, as the SDK requires.
            try:
                async with Client(self.target, read_timeout_seconds=self.read_timeout_s) as client:
                    self.client = client
                    ready.set()
                    await self._stop.wait()
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # the transport fails as an exception group
                if ready.is_set():
                    logger.warning("MCP server %s: connection lost (%s)", self.name, _cause(exc))
                else:
                    failure.append(exc)
            finally:
                self.client = None
                ready.set()

        self._task = asyncio.create_task(own(), name=f"mcp-session-{self.name}")
        try:
            await asyncio.wait_for(ready.wait(), CONNECT_TIMEOUT_S)
        except TimeoutError:
            await self.close()
            raise ServerUnavailable(f"{self.name}: no answer in {CONNECT_TIMEOUT_S:.0f}s") from None
        if failure or self.client is None:
            cause = _cause(failure[0]) if failure else "closed while connecting"
            raise ServerUnavailable(f"{self.name}: {cause}")


class McpToolClient:
    def __init__(
        self,
        servers: dict[str, str | MCPServer],
        secret: str,
        token_ttl_s: int = 60,
        read_timeout_s: float = 120.0,
    ):
        self.servers = servers  # server name -> URL or in-process server
        self.secret = secret
        self.token_ttl_s = token_ttl_s
        self.read_timeout_s = read_timeout_s
        self._sessions: dict[str, _Session] = {}

    async def connect(self) -> None:
        """Open a session to every server. Fails if any server cannot be reached."""
        self._sessions = {
            name: _Session(name, target, self.read_timeout_s)
            for name, target in self.servers.items()
        }
        try:
            for session in self._sessions.values():
                await session.get()
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        for session in self._sessions.values():
            await session.close()
        self._sessions = {}

    async def __aenter__(self) -> "McpToolClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def ping(self) -> dict[str, bool]:
        """Whether each server answers, for the health check. The protocol's own ping was
        removed in its 2026 revision, so this re-lists the tools, bypassing the client cache.
        A server that was down and is back is reconnected here."""
        status: dict[str, bool] = {}
        for name, session in self._sessions.items():
            try:
                client = await session.get()
                await client.list_tools(cache_mode="refresh")
                status[name] = True
            except Exception:
                await session.reset()
                status[name] = False
        return status

    async def list_tools(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for server, session in self._sessions.items():
            client = await session.get()
            cursor = None
            for _ in range(MAX_TOOL_PAGES):
                page = await client.list_tools(cursor=cursor)
                specs.extend(
                    ToolSpec(f"{server}.{t.name}", t.description or "", dict(t.input_schema))
                    for t in page.tools
                )
                cursor = page.next_cursor
                if cursor is None:
                    break
        return specs

    async def call(self, caller: Caller, call: ToolCall) -> ToolResult:
        server, _, tool = call.name.partition(".")
        session = self._sessions.get(server)
        if session is None or not tool:
            return ToolResult(call.id, ok=False, error="not_found")
        token = sign_caller(caller, self.secret, self.token_ttl_s)
        try:
            client = await session.get()
            result = await client.call_tool(
                tool, call.arguments, meta={envelope.CALLER_META_KEY: token}
            )
        except Exception as exc:
            # Not retried here: a tool might not be safe to run twice. The next call reconnects.
            logger.warning("MCP call %s failed: %s", call.name, _cause(exc))
            await session.reset()
            return ToolResult(call.id, ok=False, error="upstream_error")
        if result.is_error:
            message = _text(result.content)
            return ToolResult(
                call.id, ok=False, data={"message": message}, error=_error_code(message)
            )
        return envelope.to_result(call.id, result.structured_content)


def _text(content: list[Any]) -> str:
    return " ".join(getattr(item, "text", "") for item in content).strip()


def _error_code(message: str) -> ToolError:
    """A tool the server could not run: bad arguments, or a crash inside the tool."""
    return "invalid_arguments" if "validation error" in message else "upstream_error"


def _cause(exc: BaseException) -> str:
    """The innermost error of an exception group, for a readable log line."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"
