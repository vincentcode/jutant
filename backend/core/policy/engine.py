"""PolicyEngine: allow/deny and field filtering.

Used inside MCP servers, which are the trust boundary. A tool with no rule is denied.
"""

from typing import Any

from core.policy.rules import Decision, FieldRule, Rule
from core.types import Caller


class PolicyEngine:
    def __init__(self, rules: list[Rule], field_rules: list[FieldRule]):
        self.rules = rules
        self.field_rules = field_rules

    def authorize(
        self,
        caller: Caller,
        tool: str,
        arguments: dict[str, Any],
        record: dict[str, Any] | None = None,
    ) -> Decision:
        """No rule for a tool = deny. `arguments` may carry `action` and `amount`."""
        raise NotImplementedError

    def filter(self, caller: Caller, tool: str, data: Any) -> Any:
        """Remove hidden fields, recursively through dicts and lists."""
        raise NotImplementedError
