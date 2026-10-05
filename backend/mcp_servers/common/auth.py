"""Reads and verifies the caller token that comes with every tool call.

The platform signs the caller and sends the token in the request's `_meta`. A tool call with no
token, a token signed with another secret, or an expired one never reaches the tool.
"""

from mcp.server.mcpserver import Context

from core.errors import PolicyDenied
from core.policy.identity import verify_caller
from core.tools.envelope import CALLER_META_KEY
from core.types import Caller


def caller_from_context(ctx: Context, secret: str) -> Caller:
    """The verified caller for this request. Raises PolicyDenied if there is none."""
    meta = ctx.request_context.meta or {}
    token = meta.get(CALLER_META_KEY) if isinstance(meta, dict) else None
    if not isinstance(token, str):
        raise PolicyDenied("no caller token")
    return verify_caller(token, secret)
