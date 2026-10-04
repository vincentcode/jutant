"""Generic documents MCP server, shipped with the platform.

Run: python -m mcp_servers.documents.server
"""

import config.bootstrap  # noqa: F401  (sets up Django before any model is imported)
from mcp_servers.common.server import build_server, run
from mcp_servers.documents.tools import register

server = build_server("documents", port=8101)
register(server)

if __name__ == "__main__":
    run(server)
