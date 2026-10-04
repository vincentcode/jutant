from core.types import Caller
from packs.banking.policy.rules import RULES, customer_summary, same_branch


def caller(role: str, branch: str = "ACC-01") -> Caller:
    return Caller(id="S1", role=role, audience="staff", attributes={"branch": branch})


def test_every_rule_names_a_distinct_tool() -> None:
    tools = [r.tool for r in RULES]
    assert len(tools) == len(set(tools))


def test_teller_sees_own_branch_only() -> None:
    assert same_branch(caller("teller"), {}, {"branch": "ACC-01"}).allow
    assert not same_branch(caller("teller"), {}, {"branch": "KSI-02"}).allow


def test_branch_manager_sees_any_branch() -> None:
    assert same_branch(caller("branch_manager"), {}, {"branch": "KSI-02"}).allow


def test_teller_cannot_get_customer_summary() -> None:
    assert not customer_summary(caller("teller"), {}, None).allow
    assert customer_summary(caller("customer_service"), {}, {"branch": "ACC-01"}).allow
