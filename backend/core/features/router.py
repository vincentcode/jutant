"""FeatureRouter: question -> feature.

1. One feature available to the role -> return it.
2. Ask the model to choose from `id: description` lines; no tools; parse strictly.
3. Unparseable reply -> keyword scoring against feature descriptions.
4. Nothing scores -> the pack's `default_feature`.
"""

from core.features.registry import FeatureRegistry
from core.ports import ModelProvider
from core.types import Caller, Feature


class FeatureRouter:
    def __init__(self, model: ModelProvider, registry: FeatureRegistry, default: str):
        self.model = model
        self.registry = registry
        self.default = default

    async def route(self, caller: Caller, text: str) -> Feature:
        raise NotImplementedError
