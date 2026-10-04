"""Types for access rules.

A `Rule` decides whether a caller may use a tool and, once the record is fetched, whether they
may see that record. A `FieldRule` hides named fields from roles that may not see them.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from core.types import Caller


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str = ""


ALLOW = Decision(True)


class Rule(Protocol):
    tool: str

    def check(
        self, caller: Caller, arguments: dict[str, Any], record: dict[str, Any] | None
    ) -> Decision: ...


@dataclass(frozen=True)
class FunctionRule:
    """Wraps a plain function as a `Rule`, so packs can write rules as functions."""

    tool: str
    fn: Callable[[Caller, dict[str, Any], dict[str, Any] | None], Decision]

    def check(
        self, caller: Caller, arguments: dict[str, Any], record: dict[str, Any] | None
    ) -> Decision:
        return self.fn(caller, arguments, record)


@dataclass(frozen=True)
class FieldRule:
    tool: str
    hide: tuple[str, ...]
    unless_role: tuple[str, ...] = ()
