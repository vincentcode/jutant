"""FeatureRegistry: the features the loaded pack defines, and which roles may use each."""

from collections.abc import Iterable

from core.types import Feature


class FeatureRegistry:
    def __init__(self, features: Iterable[Feature]):
        self._features = {f.id: f for f in features}

    def get(self, feature_id: str) -> Feature:
        """Raises KeyError for an id the pack does not define."""
        return self._features[feature_id]

    def for_role(self, role: str) -> list[Feature]:
        return [f for f in self._features.values() if f.allows(role)]

    def __iter__(self):
        return iter(self._features.values())
