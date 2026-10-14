"""Banking and HR as one assistant: one conversation, every pack's features, each knowing its
pack, and a person seeing only the packs they have a role in."""

from pathlib import Path

from core.packs import deployment
from core.packs.loader import load_pack
from core.policy.engine import PackPolicies, PolicyEngine
from core.policy.identity import sign_caller, verify_caller
from core.types import Caller, PackRole

PACKS = Path(__file__).resolve().parents[2] / "packs"
BANKING, HR = load_pack(PACKS / "banking"), load_pack(PACKS / "hr")

AMA = Caller(
    "S0042",
    "teller",
    "staff",
    packs={
        "banking": PackRole("teller", {"branch": "ACC-01"}),
        "hr": PackRole("employee"),
    },
)


def both() -> deployment.Deployment:
    return deployment.build([BANKING, HR], "Staff Assistant")


def test_two_packs_join_with_one_conversation() -> None:
    joined = both()
    assert deployment.check(joined) == []
    ids = [f.id for f in joined.features]
    assert ids.count("conversation") == 1 and ids[0] == "conversation"
    assert {"banking.card_lookup", "hr.my_leave", "hr.leave_request"} <= set(ids)
    packs = {f.id: f.pack for f in joined.features}
    assert (packs["conversation"], packs["banking.card_lookup"], packs["hr.my_leave"]) == (
        "",
        "banking",
        "hr",
    )
    assert joined.system_prompt.startswith("You are the Staff Assistant.")
    assert joined.system_prompts["hr"].startswith("You are the HR Assistant.")
    examples = next(f for f in joined.features if f.id == "conversation").route_examples
    assert "Hello" in examples and "Hello, good morning" in examples  # both packs'


def test_one_pack_is_unchanged() -> None:
    alone = deployment.build([BANKING])
    conversation = next(f for f in alone.features if f.id == "conversation")
    assert alone.system_prompt == BANKING.system_prompt
    assert conversation.prompt == next(f for f in BANKING.features if f.id == "conversation").prompt


def test_a_person_sees_the_packs_they_have_a_role_in_with_that_role() -> None:
    joined = both()
    features = {f.id: f for f in joined.features}
    assert features["banking.card_lookup"].allows_caller(AMA)
    assert features["hr.my_leave"].allows_caller(AMA)
    assert not features["banking.customer_360"].allows_caller(AMA)  # not for tellers, as before
    banker_only = Caller("S9", "teller", "staff", packs={"banking": PackRole("teller")})
    assert not features["hr.my_leave"].allows_caller(banker_only)
    hr_as = AMA.in_pack("hr")
    assert (hr_as.role, hr_as.attributes, hr_as.pack) == ("employee", {}, "hr")
    assert AMA.in_pack("banking").attributes == {"branch": "ACC-01"}


def test_the_pack_travels_signed_and_picks_its_rules() -> None:
    caller = verify_caller(sign_caller(AMA.in_pack("hr"), "k", ttl=60), "k")
    assert (caller.role, caller.pack) == ("employee", "hr")
    policies = PackPolicies(
        {
            "banking": PolicyEngine(BANKING.rules, BANKING.field_rules),
            "hr": PolicyEngine(HR.rules, HR.field_rules),
        }
    )
    assert policies.authorize(AMA.in_pack("hr"), "documents.search", {}).allow
    assert policies.authorize(AMA.in_pack("banking"), "documents.search", {}).allow
    stranger = Caller("X", "employee", "staff", pack="payroll")
    assert not policies.authorize(stranger, "documents.search", {}).allow


def test_packs_that_cannot_be_joined_say_why() -> None:
    twice = deployment.build([BANKING, BANKING], "Staff Assistant")
    assert any(
        "feature banking.card_lookup is declared by banking and banking" in p
        for p in deployment.check(twice)
    )
    assert any(p.startswith("server cards") for p in deployment.check(twice))


def test_names_are_scoped_by_pack_with_their_references() -> None:
    joined = both()
    assert "hr.leave_request" in [a.id for a in joined.actions]
    cards = {c.title: c.feature for c in joined.home_cards}
    assert (cards["My leave"], cards["Card problems"]) == ("hr.my_leave", "banking.card_lookup")
    summary = next(f for f in joined.features if f.id == "banking.document_summary_extraction")
    assert summary.follow_ups == "banking.policy_qa"
    asked = {q["id"]: q["feature"] for q in joined.eval_questions}
    assert (asked["h03"], asked["q01"], asked["h10"]) == (
        "hr.my_leave",
        "banking.policy_qa",
        "conversation",
    )


def test_an_unscoped_name_from_before_still_finds_its_feature() -> None:
    from core.features.registry import FeatureRegistry

    registry = FeatureRegistry(both().features)
    assert registry.get("card_lookup").id == "banking.card_lookup"
    assert registry.get("conversation").id == "conversation"
