"""The staff session: a signed, expiring token in an HTTP-only cookie.

The token carries only the login name and an expiry, signed with HMAC. Who the caller is (role,
branch) is looked up fresh on every request, so a role change in the admin applies at once.
"""

import base64
import hashlib
import hmac
import json
import time

SESSION_COOKIE = "jutant_session"


class InvalidSession(Exception):
    pass


def issue_token(username: str, secret: str, ttl_min: int, now: float | None = None) -> str:
    issued = time.time() if now is None else now
    payload = _encode(json.dumps({"sub": username, "exp": int(issued + ttl_min * 60)}).encode())
    return f"{payload}.{_sign(payload, secret)}"


def verify_token(token: str, secret: str, now: float | None = None) -> str:
    """The login name in a valid token. Raises InvalidSession otherwise."""
    payload, _, signature = token.partition(".")
    if not payload or not hmac.compare_digest(signature, _sign(payload, secret)):
        raise InvalidSession("bad session token")
    try:
        body = json.loads(_decode(payload))
        username, expires = str(body["sub"]), int(body["exp"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidSession("malformed session token") from exc
    if (time.time() if now is None else now) >= expires:
        raise InvalidSession("session expired")
    return username


def _sign(payload: str, secret: str) -> str:
    return _encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
