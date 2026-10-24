from types import SimpleNamespace

import pytest

from core.features.meaning import EmbeddingIntentClassifier
from providers.intent.factory import build, build_acts
from providers.llm.fake import FakeModel
from tests.builders import FEATURES


def settings(kind: str, acts: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        JUTANT_INTENT_CLASSIFIER=kind, JUTANT_EMBED_ROUTE_PREFIX="c: ", JUTANT_ACT_CLASSIFIER=acts
    )


def test_the_default_compares_with_each_features_examples() -> None:
    classifier = build(settings("embedding"), FakeModel(), FEATURES)
    assert isinstance(classifier, EmbeddingIntentClassifier)
    assert classifier.embed_prefix == "c: "


def test_an_unknown_classifier_stops_the_start() -> None:
    with pytest.raises(ValueError, match="rasa"):
        build(settings("rasa"), FakeModel(), FEATURES)


def test_no_act_classifier_until_one_is_trained() -> None:
    assert build_acts(settings("embedding")) is None
    with pytest.raises(ValueError, match="trained"):
        build_acts(settings("embedding", acts="trained"))
