"""Runs a guarded MCP server over streamable HTTP, one process per server.

The server is stateless: it keeps no session between requests, so if it restarts, the
platform's next call simply works without reconnecting.
"""

import os
from urllib.parse import urlparse

from mcp_servers.common.guard import GuardedServer

DEFAULT_HOST = "0.0.0.0"  # inside a container; set JUTANT_MCP_HOST=127.0.0.1 to run locally


def serve(server: GuardedServer, url: str) -> None:
    """Listen on the port and path of `url`, the address the platform is configured to call."""
    address = urlparse(url)
    server.mcp.run(
        transport="streamable-http",
        host=os.environ.get("JUTANT_MCP_HOST", DEFAULT_HOST),
        port=address.port or 80,
        streamable_http_path=address.path or "/mcp",
        stateless_http=True,
        json_response=True,
    )
