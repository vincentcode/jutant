from core.features.matching import Option, best_keyword_match, parse_choice
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.types import Caller, ModelReply
from providers.llm.fake import FakeModel
from tests.builders import FEATURES, teller


def router(*replies: str) -> tuple[FeatureRouter, FakeModel]:
    model = FakeModel(replies=[ModelReply(r) for r in replies])
    return FeatureRouter(model, FeatureRegistry(FEATURES), default="policy_qa"), model


async def test_model_choice_is_used_when_it_is_an_exact_id() -> None:
    r, model = router("`transaction_lookup`.")
    feature = await r.route(teller(), "Why did my transfer fail?")
    assert feature.id == "transaction_lookup"
    prompt = model.calls[0].messages[0].content
    assert "policy_qa: Questions about policy and procedures." in prompt
    assert "customer_360" not in prompt  # not offered to a teller


async def test_unparseable_reply_falls_back_to_keywords() -> None:
    r, _ = router("I think it is about transfers, probably the lookup one")
    feature = await r.route(teller(), "Why did the transfer fail?")
    assert feature.id == "transaction_lookup"


async def test_no_keyword_match_returns_the_default() -> None:
    r, _ = router("no idea")
    feature = await r.route(teller(), "hello there")
    assert feature.id == "policy_qa"


async def test_a_role_with_one_feature_skips_the_model() -> None:
    only = FEATURES[:1]
    model = FakeModel()
    r = FeatureRouter(model, FeatureRegistry(only), default="policy_qa")
    assert (await r.route(teller(), "anything")).id == "policy_qa"
    assert model.calls == []


async def test_model_cannot_route_to_a_feature_the_role_may_not_use() -> None:
    r, _ = router("customer_360")
    feature = await r.route(teller(), "summary of customer C1001")
    assert feature.id != "customer_360"


async def test_branch_manager_is_offered_restricted_features() -> None:
    r, _ = router("customer_360")
    manager = Caller("S9", "branch_manager", "staff", {})
    assert (await r.route(manager, "summary of customer C1001")).id == "customer_360"


def test_parse_choice_is_strict() -> None:
    ids = ["policy_qa", "transaction_lookup"]
    assert parse_choice(' "Policy_QA" ', ids) == "policy_qa"
    assert parse_choice("policy_qa or transaction_lookup", ids) is None
    assert parse_choice("", ids) is None


def test_keyword_match_folds_plurals() -> None:
    options = [Option("a", "Recent transfers and payments"), Option("b", "Bank policy")]
    assert best_keyword_match("a transfer that failed", options) == "a"
    assert best_keyword_match("weather today", options) is None
