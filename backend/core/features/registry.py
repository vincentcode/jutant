"""FeatureRegistry: the features the loaded packs define, and who may use each."""

from collections.abc import Iterable

from core.types import Caller, Feature


class FeatureRegistry:
    def __init__(self, features: Iterable[Feature]):
        self._features = {f.id: f for f in features}

    def get(self, feature_id: str) -> Feature:
        """Raises KeyError for an id no loaded pack defines. With several packs a feature is
        named by its pack (`hr.my_leave`); a name without its pack (kept from before, in a
        conversation's context) finds it while only one pack has a feature of that name."""
        found = self._features.get(feature_id)
        if found is not None:
            return found
        named = [f for f in self._features.values() if f.id.endswith(f".{feature_id}")]
        if len(named) == 1:
            return named[0]
        raise KeyError(feature_id)

    def for_role(self, role: str) -> list[Feature]:
        return [f for f in self._features.values() if f.allows(role)]

    def for_caller(self, caller: Caller) -> list[Feature]:
        """The features `caller` may use: in every pack they have a role in, those that role
        may use."""
        return [f for f in self._features.values() if f.allows_caller(caller)]

    def __iter__(self):
        return iter(self._features.values())
