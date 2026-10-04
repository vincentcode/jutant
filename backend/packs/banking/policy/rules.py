"""Banking access rules. Defaults, to confirm with the bank.

Rules are plain functions wrapped as `Rule` objects, testable without Django. A rule that needs
the record is called twice by `@guarded_tool`: before the fetch (`record=None`) and after.
"""

from typing import Any

from core.policy.rules import ALLOW, Decision, FunctionRule, Rule
from core.types import Caller

ALL_STAFF = frozenset({"teller", "customer_service", "credit_officer", "branch_manager"})
SUMMARY_ROLES = frozenset({"customer_service", "credit_officer", "branch_manager"})


def any_staff(caller: Caller, arguments: dict[str, Any], record: dict[str, Any] | None) -> Decision:
    if caller.role in ALL_STAFF:
        return ALLOW
    return Decision(False, "role")


def same_branch(
    caller: Caller, arguments: dict[str, Any], record: dict[str, Any] | None
) -> Decision:
    """Branch manager: any record. Others: the record's branch must equal the caller's."""
    if caller.role not in ALL_STAFF:
        return Decision(False, "role")
    if caller.role == "branch_manager" or record is None:
        return ALLOW
    if record.get("branch") == caller.attributes.get("branch"):
        return ALLOW
    return Decision(False, "branch")


def customer_summary(
    caller: Caller, arguments: dict[str, Any], record: dict[str, Any] | None
) -> Decision:
    if caller.role not in SUMMARY_ROLES:
        return Decision(False, "role")
    return same_branch(caller, arguments, record)


RULES: list[Rule] = [
    FunctionRule("documents.search", any_staff),
    FunctionRule("documents.get", any_staff),
    FunctionRule("services.search_products", any_staff),
    FunctionRule("services.get_product", any_staff),
    FunctionRule("services.get_requirements", any_staff),
    FunctionRule("transactions.list", same_branch),
    FunctionRule("transactions.get_status", same_branch),
    FunctionRule("services.customer_summary", customer_summary),
]
