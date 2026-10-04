"""documents.search and documents.get.

The caller's readable classifications come from the pack manifest and are applied in the selector.
"""

from mcp.server.fastmcp import FastMCP


def register(server: FastMCP) -> None:
    """Register `search(query, doc_type?, limit=4)` and `get(document_id)` under @guarded_tool."""
    raise NotImplementedError
