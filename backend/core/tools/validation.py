"""Checks a tool call's arguments before it runs.

Arguments must match the tool's JSON schema, and identity arguments are removed: who the
caller is comes from their login, never from the model.
"""

from typing import Any

IDENTITY_ARGUMENTS = frozenset({"caller", "role", "staff_id", "user_id"})


def validate_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return schema violations; empty when the arguments are valid."""
    raise NotImplementedError


def strip_identity(arguments: dict[str, Any]) -> dict[str, Any]:
    """Remove any argument named like identity. The model must not supply identity."""
    raise NotImplementedError
