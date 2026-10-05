"""Signs and verifies the caller token sent with every tool call.

The platform signs who the caller is (HMAC over JSON, short expiry). Each MCP server verifies
the token before running a tool, so no tool trusts an identity it cannot check.

Token format: `<base64url(json payload)>.<base64url(hmac-sha256 of the payload part)>`.
"""

import base64
import hashlib
import hmac
import json
import time

from core.errors import PolicyDenied
from core.types import Caller


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signature(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def sign_caller(caller: Caller, secret: str, ttl: int, now: float | None = None) -> str:
    """Return a token carrying `caller`, valid for `ttl` seconds."""
    issued = time.time() if now is None else now
    body = {
        "id": caller.id,
        "role": caller.role,
        "audience": caller.audience,
        "attributes": caller.attributes,
        "exp": int(issued + ttl),
    }
    payload = _b64encode(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    return f"{payload}.{_signature(payload, secret)}"


def verify_caller(token: str, secret: str, now: float | None = None) -> Caller:
    """Return the caller in `token`. Raises PolicyDenied if malformed, tampered or expired."""
    payload, _, signature = token.partition(".")
    if not payload or not signature:
        raise PolicyDenied("malformed caller token")
    if not hmac.compare_digest(signature, _signature(payload, secret)):
        raise PolicyDenied("bad caller token signature")
    try:
        body = json.loads(_b64decode(payload))
        expires = int(body["exp"])
        caller = Caller(
            id=str(body["id"]),
            role=str(body["role"]),
            audience=str(body["audience"]),
            attributes=dict(body.get("attributes") or {}),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise PolicyDenied("malformed caller token") from exc
    if (time.time() if now is None else now) >= expires:
        raise PolicyDenied("caller token expired")
    return caller
