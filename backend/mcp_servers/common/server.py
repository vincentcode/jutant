"""Runs a guarded MCP server over streamable HTTP, one process per server.

The server is stateless: it keeps no session between requests, so if it restarts, the
platform's next call simply works without reconnecting.
"""

import os
from urllib.parse import urlparse

from mcp_servers.common.guard import GuardedServer
from providers import tracing

DEFAULT_HOST = "0.0.0.0"  # inside a container; set JUTANT_MCP_HOST=127.0.0.1 to run locally


def serve(server: GuardedServer, url: str) -> None:
    """Listen on the port and path of `url`, the address the platform is configured to call.

    Tracing is set up from the environment (JUTANT_TRACING_*), as the API's is, so this
    server's spans join the platform's traces."""
    server.tracer, server.trace_content = tracing.from_env(f"jutant-mcp-{server.name}")
    address = urlparse(url)
    try:
        server.mcp.run(
            transport="streamable-http",
            host=os.environ.get("JUTANT_MCP_HOST", DEFAULT_HOST),
            port=address.port or 80,
            streamable_http_path=address.path or "/mcp",
            stateless_http=True,
            json_response=True,
        )
    finally:
        shutdown = getattr(server.tracer, "shutdown", None)
        if shutdown is not None:
            shutdown()  # sends the spans still waiting
