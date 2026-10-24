"""Build the intent classifier from settings: the router's meaning step. A new classifier (Rasa
NLU in its own container, or one trained on embeddings) is one file and one branch here."""

from collections.abc import Iterable
from typing import Any

from core.features.meaning import EmbeddingIntentClassifier
from core.ports import IntentClassifier, ModelProvider
from core.types import Feature


def build(settings: Any, model: ModelProvider, features: Iterable[Feature]) -> IntentClassifier:
    kind = settings.JUTANT_INTENT_CLASSIFIER
    if kind == "embedding":
        return EmbeddingIntentClassifier(model, features, settings.JUTANT_EMBED_ROUTE_PREFIX)
    raise ValueError(f"Unknown JUTANT_INTENT_CLASSIFIER: {kind}")
