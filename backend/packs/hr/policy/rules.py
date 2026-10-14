"""HR access rules. Defaults, to confirm with HR.

Every HR tool is for the caller's own record (the staff number comes from the signed caller,
never an argument), so the rules only check that the caller is an employee. Rules for managers
and HR staff, who may see others' records, come with the features that need them.
"""

from typing import Any

from core.policy.rules import ALLOW, Decision, FunctionRule, Rule
from core.types import Caller

EMPLOYEES = frozenset({"employee"})


def own_record(
    caller: Caller, arguments: dict[str, Any], record: dict[str, Any] | None
) -> Decision:
    if caller.role in EMPLOYEES:
        return ALLOW
    return Decision(False, "role")


TOOLS = (
    "documents.search",
    "documents.get",
    "hr.my_profile",
    "hr.leave_balance",
    "hr.leave_types",
    "hr.holidays",
    "hr.my_requests",
    "hr.get_request",
    "hr.propose_leave_request",
    "hr.propose_help_request",
    "hr.propose_comment",
    "hr.propose_contact",
    "hr.submit_leave_request",
    "hr.submit_help_request",
    "hr.submit_comment",
    "hr.submit_contact",
)

RULES: list[Rule] = [FunctionRule(tool, own_record) for tool in TOOLS]
