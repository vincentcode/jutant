"""Checks a tool call's arguments before it runs.

Arguments must match the tool's JSON schema, and identity arguments are removed: who the
caller is comes from their login, never from the model.
"""

from typing import Any

from jsonschema import Draft202012Validator

IDENTITY_ARGUMENTS = frozenset({"caller", "role", "staff_id", "user_id"})


def validate_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return schema violations as short readable lines; empty when the arguments are valid.

    The lines are sent back to the model so it can correct the call, so they stay short.
    """
    validator = Draft202012Validator(schema)
    problems = []
    for error in sorted(validator.iter_errors(arguments), key=lambda e: list(e.path)):
        where = ".".join(str(p) for p in error.path)
        problems.append(f"{where}: {error.message}" if where else error.message)
    return problems


def strip_identity(arguments: dict[str, Any]) -> dict[str, Any]:
    """Remove any argument named like identity. The model must not supply identity."""
    return {k: v for k, v in arguments.items() if k not in IDENTITY_ARGUMENTS}
