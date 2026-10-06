"""FeatureRouter: decides which feature answers a question.

Cheapest and surest first, so the model (about 30 seconds a call on a CPU) is asked only when
nothing else is sure:

1. One feature available to the role: use it.
2. Patterns: the pack's route patterns (a customer number, a transfer reference). Decides only
   if exactly one available feature matches.
3. Meaning: the question's embedding against each feature's example questions and description.
   Decides only if the best feature is similar enough and clearly ahead of the next.
4. The model chooses from `id: description` lines; only an exact id is accepted.
5. Keyword scoring against the descriptions, then the pack's default feature.

A preferred feature changes this. Another feature's pattern (and not the preferred one's)
still decides. Then:

- Staff's quick action (`prefer`) may be left over from an earlier question. It is kept if its
  meaning is the closest or near it; if another feature is clearly closer, the question is routed
  as usual, from the meaning step, and the model may still choose the quick action.
- A follow-up's feature (`continuing`) is about the same thing by construction. It is kept unless
  another feature's meaning is clearly ahead: similar enough, and by the margin. The model is not
  asked.

The embedding model scores most features between 0.7 and 0.8 for any banking question, so
"clearly ahead" is rare: on its own, the stricter rule would almost never leave a quick action.

The step that decided is recorded in the audit log, so a shortcut that misroutes can be found.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from core.errors import ModelUnavailable
from core.features.matching import Option, ask_model, best_keyword_match
from core.features.registry import FeatureRegistry
from core.ports import ModelProvider
from core.types import Caller, Feature

INSTRUCTION = "Choose the feature that best matches the staff member's question."
MIN_SIMILARITY = 0.80
MIN_MARGIN = 0.05

RoutedBy = Literal["only", "pattern", "meaning", "preferred", "model", "keywords", "default"]


@dataclass(frozen=True)
class Route:
    feature: Feature
    by: RoutedBy
    score: float | None = None  # the similarity, when routed by meaning


class FeatureRouter:
    def __init__(
        self,
        model: ModelProvider,
        registry: FeatureRegistry,
        default: str,
        *,
        embed_prefix: str = "",
        min_similarity: float = MIN_SIMILARITY,
        min_margin: float = MIN_MARGIN,
    ):
        self.model = model
        self.registry = registry
        self.default = default
        self.embed_prefix = embed_prefix  # the embedding model's prefix for comparing texts
        self.min_similarity = min_similarity
        self.min_margin = min_margin
        self._patterns = {f.id: [re.compile(p) for p in f.route_patterns] for f in registry}
        self._examples: dict[str, list[list[float]]] | None = None  # embedded on first use

    async def route(
        self,
        caller: Caller,
        text: str,
        model: ModelProvider | None = None,
        prefer: str | None = None,
        continuing: str | None = None,
    ) -> Route:
        """`model` stands in for the router's own for this question (a traced one, say).
        `prefer`: staff's quick action; `continuing`: for a follow-up, the feature that answered
        last. A feature the role may not use is ignored."""
        model = model or self.model
        available = self.registry.for_role(caller.role)
        if not available:
            raise LookupError(f"No features for role {caller.role}")
        if len(available) == 1:
            return Route(available[0], "only")
        by_id = {f.id: f for f in available}
        preferred = by_id.get(prefer or continuing or "")
        matched = self._matching(text, available)
        if preferred is not None and preferred in matched:
            return Route(preferred, "preferred")
        if len(matched) == 1:
            return Route(matched[0], "pattern")

        scored = await self._scores(text, available, model)
        if preferred is not None:
            own = next((score for score, f in scored if f is preferred), 0.0)
            best = scored[0][0] if scored else 0.0
            if prefer is not None and best - own < self.min_margin:
                return Route(preferred, "preferred")  # the quick action is (nearly) the closest
            if prefer is None and not self._clear(scored, own):
                return Route(preferred, "preferred")  # a follow-up stays unless clearly elsewhere
        if (route := self._by_meaning(scored)) is not None:
            return route
        options = [Option(f.id, f.description) for f in available]
        if chosen := await ask_model(model, INSTRUCTION, text, options):
            return Route(by_id[chosen], "model")
        if chosen := best_keyword_match(text, options):
            return Route(by_id[chosen], "keywords")
        return Route(by_id.get(self.default, available[0]), "default")

    def _clear(self, scored: list[tuple[float, Feature]], other: float) -> bool:
        """The closest feature is similar enough, and ahead of `other` by the margin."""
        return (
            bool(scored)
            and scored[0][0] >= self.min_similarity
            and (scored[0][0] - other >= self.min_margin)
        )

    def _matching(self, text: str, available: Sequence[Feature]) -> list[Feature]:
        return [f for f in available if any(p.search(text) for p in self._patterns[f.id])]

    async def _scores(
        self, text: str, available: Sequence[Feature], model: ModelProvider
    ) -> list[tuple[float, Feature]]:
        """Each feature's best similarity to the question, highest first; empty if the
        features have no examples or the embedding model cannot be reached."""
        try:
            examples = await self._embedded_examples()
            if not any(examples.get(f.id) for f in available):
                return []  # nothing to compare with: do not embed the question
            [question] = await model.embed([self.embed_prefix + text])
        except ModelUnavailable:
            return []
        return sorted(
            (
                (max(_cosine(question, e) for e in examples[f.id]), f)
                for f in available
                if examples.get(f.id)
            ),
            key=lambda pair: -pair[0],
        )

    def _by_meaning(self, scored: list[tuple[float, Feature]]) -> Route | None:
        if not scored:
            return None
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        if self._clear(scored, runner_up):
            return Route(scored[0][1], "meaning", round(scored[0][0], 3))
        return None

    async def _embedded_examples(self) -> dict[str, list[list[float]]]:
        """Each feature's examples and description, embedded once and kept."""
        if self._examples is None:
            texts = [
                (f.id, t)
                for f in self.registry
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
