from types import SimpleNamespace

import pytest

from core.features.meaning import EmbeddingIntentClassifier
from providers.intent.factory import build
from providers.llm.fake import FakeModel
from tests.builders import FEATURES


def settings(kind: str) -> SimpleNamespace:
    return SimpleNamespace(JUTANT_INTENT_CLASSIFIER=kind, JUTANT_EMBED_ROUTE_PREFIX="c: ")


def test_the_default_compares_with_each_features_examples() -> None:
    classifier = build(settings("embedding"), FakeModel(), FEATURES)
    assert isinstance(classifier, EmbeddingIntentClassifier)
    assert classifier.embed_prefix == "c: "


def test_an_unknown_classifier_stops_the_start() -> None:
    with pytest.raises(ValueError, match="rasa"):
        build(settings("rasa"), FakeModel(), FEATURES)
