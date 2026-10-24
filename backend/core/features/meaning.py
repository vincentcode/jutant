"""The default intent classifier: a question compared by meaning with each feature's example
questions and description (`IntentClassifier`).

Each feature's examples and description are embedded once, on first use; the question is
embedded each time, and a feature's score is its closest example's cosine similarity. Nothing is
trained: a pack's examples are the classifier, so adding an example changes it at once.
"""

import math
from collections.abc import Iterable, Sequence

from core.errors import ModelUnavailable
from core.ports import ModelProvider
from core.types import Feature


class EmbeddingIntentClassifier:
    def __init__(self, model: ModelProvider, features: Iterable[Feature], embed_prefix: str = ""):
        self.model = model
        self.features = tuple(features)
        self.embed_prefix = embed_prefix  # the embedding model's prefix for comparing texts
        self._examples: dict[str, list[list[float]]] | None = None  # embedded on first use

    async def scores(
        self, text: str, features: Sequence[Feature], model: ModelProvider | None = None
    ) -> list[tuple[float, Feature]]:
        try:
            examples = await self._embedded_examples()
            if not any(examples.get(f.id) for f in features):
                return []  # nothing to compare with: do not embed the question
            [question] = await (model or self.model).embed([self.embed_prefix + text])
        except ModelUnavailable:
            return []
        return sorted(
            (
                (max(_cosine(question, e) for e in examples[f.id]), f)
                for f in features
                if examples.get(f.id)
            ),
            key=lambda pair: -pair[0],
        )

    async def _embedded_examples(self) -> dict[str, list[list[float]]]:
        """Each feature's examples and description, embedded once and kept."""
        if self._examples is None:
            texts = [
                (f.id, t)
                for f in self.features
                if f.route_examples
                for t in (*f.route_examples, f.description)
            ]
            vectors = await self.model.embed([self.embed_prefix + t for _, t in texts])
            examples: dict[str, list[list[float]]] = {}
            for (feature_id, _), vector in zip(texts, vectors, strict=True):
                examples.setdefault(feature_id, []).append(vector)
            self._examples = examples
        return self._examples


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
