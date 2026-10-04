"""Signs and verifies the caller token sent with every tool call.

The platform signs who the caller is (HMAC over JSON, short expiry). Each MCP server verifies
the token before running a tool, so no tool trusts an identity it cannot check.
"""

from core.types import Caller


def sign_caller(caller: Caller, secret: str, ttl: int) -> str:
    """Return a token carrying `caller`, valid for `ttl` seconds."""
    raise NotImplementedError


def verify_caller(token: str, secret: str) -> Caller:
    """Return the caller in `token`. Raises PolicyDenied if invalid or expired."""
    raise NotImplementedError
