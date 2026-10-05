import pytest

from core.errors import PolicyDenied
from core.policy.engine import PolicyEngine
from core.policy.identity import sign_caller, verify_caller
from core.policy.rules import ALLOW, Decision, FieldRule, FunctionRule
from core.types import Caller


def caller(role: str = "handler", **attributes: str) -> Caller:
    return Caller(id="S1", role=role, audience="staff", attributes=attributes)


def same_team(c: Caller, arguments: dict, record: dict | None) -> Decision:
    if record is None or record.get("team") == c.attributes.get("team"):
        return ALLOW
    return Decision(False, "team")


def test_tool_with_no_rule_is_denied() -> None:
    engine = PolicyEngine([FunctionRule("records.get", lambda c, a, r: ALLOW)])
    decision = engine.authorize(caller(), "records.delete", {})
    assert not decision.allow
    assert decision.reason == "no_rule"


def test_rule_sees_the_record_on_second_check() -> None:
    engine = PolicyEngine([FunctionRule("records.get", same_team)])
    me = caller(team="A")
    assert engine.authorize(me, "records.get", {}).allow
    assert engine.authorize(me, "records.get", {}, record={"team": "A"}).allow
    assert engine.authorize(me, "records.get", {}, record={"team": "B"}).reason == "team"


def test_every_rule_for_a_tool_must_allow() -> None:
    engine = PolicyEngine(
        [
            FunctionRule("records.get", lambda c, a, r: ALLOW),
            FunctionRule("records.get", lambda c, a, r: Decision(False, "limit")),
        ]
    )
    assert engine.authorize(caller(), "records.get", {}).reason == "limit"


def test_rule_can_read_action_and_amount() -> None:
    def within_limit(c: Caller, a: dict, r: dict | None) -> Decision:
        return Decision(a.get("amount", 0) <= 1000, "authority_limit")

    engine = PolicyEngine([FunctionRule("records.pay", within_limit)])
    assert engine.authorize(caller(), "records.pay", {"action": "pay", "amount": 500}).allow
    assert not engine.authorize(caller(), "records.pay", {"action": "pay", "amount": 5000}).allow


def test_field_filtering_reaches_nested_data() -> None:
    engine = PolicyEngine(
        [], [FieldRule("records.get", hide=("secret",), unless_role=("supervisor",))]
    )
    data = {
        "id": 1,
        "secret": "x",
        "items": [{"name": "a", "secret": "y"}, {"name": "b"}],
        "nested": {"deep": {"secret": "z", "keep": True}},
    }
    assert engine.filter(caller(), "records.get", data) == {
        "id": 1,
        "items": [{"name": "a"}, {"name": "b"}],
        "nested": {"deep": {"keep": True}},
    }
    assert engine.filter(caller("supervisor"), "records.get", data) == data


def test_field_rules_apply_only_to_their_tool() -> None:
    engine = PolicyEngine([], [FieldRule("records.get", hide=("secret",))])
    assert engine.filter(caller(), "records.list", {"secret": 1}) == {"secret": 1}


def test_caller_token_round_trip() -> None:
    original = caller(team="A")
    token = sign_caller(original, "s3cret", ttl=60, now=1000)
    assert verify_caller(token, "s3cret", now=1030) == original


def test_caller_token_rejects_wrong_secret_tampering_and_expiry() -> None:
    token = sign_caller(caller(), "s3cret", ttl=60, now=1000)
    with pytest.raises(PolicyDenied):
        verify_caller(token, "other", now=1000)
    payload, signature = token.split(".")
    forged = sign_caller(caller("supervisor"), "s3cret", ttl=60, now=1000).split(".")[0]
    with pytest.raises(PolicyDenied):
        verify_caller(f"{forged}.{signature}", "s3cret", now=1000)
    with pytest.raises(PolicyDenied):
        verify_caller(token, "s3cret", now=1060)
    with pytest.raises(PolicyDenied):
        verify_caller("not-a-token", "s3cret")
