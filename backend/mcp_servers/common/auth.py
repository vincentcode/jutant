"""Verify the caller token on every request.

Missing or expired token -> the request is rejected.
"""

from mcp.server.fastmcp import Context

from core.types import Caller

CALLER_HEADER = "x-jutant-caller"


def caller_from_context(ctx: Context, secret: str) -> Caller:
    raise NotImplementedError
