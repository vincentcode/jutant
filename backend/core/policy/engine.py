"""PolicyEngine: allow/deny and field filtering.

Used inside MCP servers, which are the trust boundary. A tool with no rule is denied.
"""

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from core.policy.rules import Decision, FieldRule, Rule
from core.types import Caller

NO_RULE = Decision(False, "no_rule")


class PolicyEngine:
    def __init__(self, rules: Iterable[Rule], field_rules: Iterable[FieldRule] = ()):
        self.rules: dict[str, list[Rule]] = defaultdict(list)
        for rule in rules:
            self.rules[rule.tool].append(rule)
        self.field_rules: dict[str, list[FieldRule]] = defaultdict(list)
        for field_rule in field_rules:
            self.field_rules[field_rule.tool].append(field_rule)

    def authorize(
        self,
        caller: Caller,
        tool: str,
        arguments: dict[str, Any],
        record: dict[str, Any] | None = None,
    ) -> Decision:
        """Every rule for the tool must allow. No rule for a tool = deny.

        `arguments` may carry `action` and `amount`, so rules can enforce authority limits once
        write tools exist.
        """
        rules = self.rules.get(tool)
        if not rules:
            return NO_RULE
        for rule in rules:
            decision = rule.check(caller, arguments, record)
            if not decision.allow:
                return decision
        return Decision(True)

    def hidden_fields(self, caller: Caller, tool: str) -> frozenset[str]:
        return frozenset(
            name
            for rule in self.field_rules.get(tool, ())
            if caller.role not in rule.unless_role
            for name in rule.hide
        )

    def filter(self, caller: Caller, tool: str, data: Any) -> Any:
        """Remove hidden fields, recursively through dicts and lists."""
        hidden = self.hidden_fields(caller, tool)
        return _strip(data, hidden) if hidden else data


def _strip(data: Any, hidden: frozenset[str]) -> Any:
    if isinstance(data, dict):
        return {k: _strip(v, hidden) for k, v in data.items() if k not in hidden}
    if isinstance(data, list | tuple):
        return [_strip(item, hidden) for item in data]
    return data
