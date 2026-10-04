"""Session token: issue, verify, cookie settings.

Signed token in an HTTP-only, SameSite=Strict, Secure cookie.
"""

SESSION_COOKIE = "jutant_session"


def issue_token(user_id: str, secret: str, ttl_min: int) -> str:
    raise NotImplementedError


def verify_token(token: str, secret: str) -> str:
    """Return the user id in a valid token."""
    raise NotImplementedError
