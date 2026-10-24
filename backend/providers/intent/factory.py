"""Build the classifiers that read a message from settings: the router's meaning step (the
intent) and, if one is set, the dialogue act classifier. A new classifier (Rasa NLU in its own
container, or one trained on embeddings) is one file and one branch here."""

from collections.abc import Iterable
from typing import Any

from core.features.meaning import EmbeddingIntentClassifier
from core.ports import DialogueActClassifier, IntentClassifier, ModelProvider
from core.types import Feature


def build(settings: Any, model: ModelProvider, features: Iterable[Feature]) -> IntentClassifier:
    kind = settings.JUTANT_INTENT_CLASSIFIER
    if kind == "embedding":
        return EmbeddingIntentClassifier(model, features, settings.JUTANT_EMBED_ROUTE_PREFIX)
    raise ValueError(f"Unknown JUTANT_INTENT_CLASSIFIER: {kind}")


def build_acts(settings: Any) -> DialogueActClassifier | None:
    """None until one is trained: the code rules and the model's questions read each turn."""
    kind = settings.JUTANT_ACT_CLASSIFIER
    if not kind:
        return None
    raise ValueError(f"Unknown JUTANT_ACT_CLASSIFIER: {kind}")
