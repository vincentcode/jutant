"""FeatureRegistry: the features the loaded pack defines, and which roles may use each."""

from collections.abc import Iterable

from core.types import Feature


class FeatureRegistry:
    def __init__(self, features: Iterable[Feature]):
        self._features = {f.id: f for f in features}

    def get(self, feature_id: str) -> Feature:
        raise NotImplementedError

    def for_role(self, role: str) -> list[Feature]:
        raise NotImplementedError
