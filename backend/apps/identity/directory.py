"""Verifies credentials against the client's directory (LDAP or OIDC).

In development it checks Django's user table. Used by the API login and by `backends.py`.
"""

from typing import Any


def verify(username: str, password: str) -> dict[str, Any] | None:
    """Return the directory attributes for a valid login, or None."""
    raise NotImplementedError
