"""Verifies credentials against the client's directory (LDAP or OIDC).

Each client's directory is different, so the real check is written per deployment. In
development the "directory" is Django's own user table. Used by the API login and by the
admin login backend.
"""

from typing import Any

from apps.identity import selectors


def verify(username: str, password: str) -> dict[str, Any] | None:
    """The directory's attributes for a valid login, or None.

    The returned dict may carry `first_name`, `last_name`, `email`, `staff_number`, `role` and
    `attributes`; `services.sync_from_directory` copies whichever are present.
    """
    user = selectors.user_with_password(username=username, password=password)
    if user is None:
        return None
    return {"first_name": user.first_name, "last_name": user.last_name, "email": user.email}
