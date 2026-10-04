"""Shared server bootstrap: a FastMCP server over streamable HTTP, one process per server."""

from mcp.server.fastmcp import FastMCP


def build_server(name: str, port: int) -> FastMCP:
    return FastMCP(name, host="0.0.0.0", port=port, stateless_http=True)


def run(server: FastMCP) -> None:
    server.run(transport="streamable-http")
