"""McpToolClient: implements core.ports.ToolClient over streamable HTTP.

One session per server. Tool names are prefixed with the server name. The caller is signed with
`core.policy.identity.sign_caller` and sent as a request header, never as a tool argument.
MCP errors map to `ToolResult(ok=False, error=...)`.
"""

from core.types import Caller, ToolCall, ToolResult, ToolSpec

CALLER_HEADER = "X-Jutant-Caller"


class McpToolClient:
    def __init__(self, servers: dict[str, str], secret: str, token_ttl_s: int = 60):
        self.servers = servers  # server name -> URL
        self.secret = secret
        self.token_ttl_s = token_ttl_s

    async def connect(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

    async def list_tools(self) -> list[ToolSpec]:
        raise NotImplementedError

    async def call(self, caller: Caller, call: ToolCall) -> ToolResult:
        raise NotImplementedError
