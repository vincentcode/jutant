from dataclasses import replace

from core.errors import ModelUnavailable
from core.features.matching import Option, best_keyword_match, parse_choice
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.types import Caller, ModelReply
from providers.llm.fake import FakeModel
from tests.builders import FEATURES, teller


def router(*replies: str, features=FEATURES) -> tuple[FeatureRouter, FakeModel]:
    model = FakeModel(replies=[ModelReply(r) for r in replies])
    return FeatureRouter(model, FeatureRegistry(features), default="policy_qa"), model


def with_route(feature_id: str, patterns=(), examples=()):
    """FEATURES, with route patterns or examples on one feature."""
    return [
        replace(f, route_patterns=tuple(patterns), route_examples=tuple(examples))
        if f.id == feature_id
        else f
        for f in FEATURES
    ]


class TopicModel(FakeModel):
    """Embeds a text as a vector of the topic words it contains, so similarity is
    predictable."""

    TOPICS = ("transfer", "policy", "card", "id")

    async def embed(self, texts):
        return [[1.0 if t in text.lower() else 0.0 for t in self.TOPICS] for text in texts]


async def test_model_choice_is_used_when_it_is_an_exact_id() -> None:
    r, model = router("`transaction_lookup`.")
    route = await r.route(teller(), "Why did my transfer fail?")
    assert route.feature.id == "transaction_lookup" and route.by == "model"
    prompt = model.calls[0].messages[0].content
    assert "policy_qa: Questions about policy and procedures." in prompt
    assert "customer_360" not in prompt  # not offered to a teller


async def test_unparseable_reply_falls_back_to_keywords() -> None:
    r, _ = router("I think it is about transfers, probably the lookup one")
    route = await r.route(teller(), "Why did the transfer fail?")
    assert route.feature.id == "transaction_lookup" and route.by == "keywords"


async def test_no_keyword_match_returns_the_default() -> None:
    r, _ = router("no idea")
    route = await r.route(teller(), "hello there")
    assert route.feature.id == "policy_qa" and route.by == "default"


async def test_a_role_with_one_feature_skips_the_model() -> None:
    only = FEATURES[:1]
    model = FakeModel()
    r = FeatureRouter(model, FeatureRegistry(only), default="policy_qa")
    assert (await r.route(teller(), "anything")).by == "only"
    assert model.calls == []


async def test_model_cannot_route_to_a_feature_the_role_may_not_use() -> None:
    r, _ = router("customer_360")
    route = await r.route(teller(), "summary of customer C1001")
    assert route.feature.id != "customer_360"


async def test_branch_manager_is_offered_restricted_features() -> None:
    r, _ = router("customer_360")
    manager = Caller("S9", "branch_manager", "staff", {})
    assert (await r.route(manager, "summary of customer C1001")).feature.id == "customer_360"


# --- patterns -----------------------------------------------------------------------------


async def test_a_pattern_routes_without_the_model() -> None:
    r, model = router(features=with_route("transaction_lookup", patterns=[r"\bTX-\d+\b"]))
    route = await r.route(teller(), "Why did TX-0002 fail?")
    assert route.feature.id == "transaction_lookup" and route.by == "pattern"
    assert model.calls == []


async def test_patterns_of_two_features_leave_it_to_the_next_step() -> None:
    features = [
        replace(f, route_patterns=(r"\bTX-\d+\b",))
        if f.id in ("transaction_lookup", "policy_qa")
        else f
        for f in FEATURES
    ]
    r, _ = router("transaction_lookup", features=features)
    assert (await r.route(teller(), "Why did TX-0002 fail?")).by == "model"


async def test_a_pattern_of_a_feature_the_role_may_not_use_is_ignored() -> None:
    r, _ = router("policy_qa", features=with_route("customer_360", patterns=[r"\bC\d{4}\b"]))
    route = await r.route(teller(), "summary of customer C1001")
    assert route.feature.id != "customer_360" and route.by == "model"


# --- meaning ------------------------------------------------------------------------------


async def test_a_close_match_by_meaning_routes_without_the_model() -> None:
    model = TopicModel()
    features = with_route("transaction_lookup", examples=["a transfer went missing"])
    r = FeatureRouter(model, FeatureRegistry(features), default="policy_qa")
    route = await r.route(teller(), "Where is my transfer?")
    assert route.feature.id == "transaction_lookup" and route.by == "meaning"
    assert route.score == 1.0 and model.calls == []


async def test_examples_are_embedded_once() -> None:
    class Counting(TopicModel):
        embedded = 0

        async def embed(self, texts):
            Counting.embedded += len(texts)
            return await super().embed(texts)

    features = with_route("transaction_lookup", examples=["a transfer went missing"])
    r = FeatureRouter(Counting(), FeatureRegistry(features), default="policy_qa")
    await r.route(teller(), "Where is my transfer?")
    await r.route(teller(), "Has the transfer arrived?")
    assert Counting.embedded == 2 + 2  # the example and description once, then each question


async def test_a_weak_match_by_meaning_leaves_it_to_the_model() -> None:
    model = TopicModel(replies=[ModelReply("policy_qa")])
    features = with_route("transaction_lookup", examples=["a transfer went missing"])
    r = FeatureRouter(model, FeatureRegistry(features), default="policy_qa")
    route = await r.route(teller(), "What is the card policy?")  # shares no topic
    assert route.by == "model" and route.feature.id == "policy_qa"


async def test_two_features_equally_close_leave_it_to_the_model() -> None:
    features = [
        replace(f, route_examples=("transfer rules",))
        if f.id in ("transaction_lookup", "policy_qa")
        else f
        for f in FEATURES
    ]
    model = TopicModel(replies=[ModelReply("transaction_lookup")])
    r = FeatureRouter(model, FeatureRegistry(features), default="policy_qa", min_margin=0.05)
    assert (await r.route(teller(), "transfer rules?")).by == "model"


async def test_without_embeddings_the_model_decides() -> None:
    class NoEmbeddings(FakeModel):
        async def embed(self, texts):
            raise ModelUnavailable("down")

    features = with_route("transaction_lookup", examples=["a transfer went missing"])
    model = NoEmbeddings(replies=[ModelReply("transaction_lookup")])
    r = FeatureRouter(model, FeatureRegistry(features), default="policy_qa")
    assert (await r.route(teller(), "Where is my transfer?")).by == "model"


# --- matching helpers ---------------------------------------------------------------------


def test_parse_choice_is_strict() -> None:
    ids = ["policy_qa", "transaction_lookup"]
    assert parse_choice(' "Policy_QA" ', ids) == "policy_qa"
    assert parse_choice("policy_qa or transaction_lookup", ids) is None
    assert parse_choice("", ids) is None


def test_keyword_match_folds_plurals() -> None:
    options = [Option("a", "Recent transfers and payments"), Option("b", "Bank policy")]
    assert best_keyword_match("a transfer that failed", options) == "a"
    assert best_keyword_match("weather today", options) is None
