"""FeatureRouter: decides which feature answers a question.

1. One feature available to the role: use it.
2. Ask the model to choose from `id: description` lines, with no tools; accept only an exact id.
3. Unparseable reply: keyword scoring against the feature descriptions.
4. Nothing scores: the pack's default feature (or the role's first feature if the default is
   not open to the role).

Staff can also pick a feature in the client, which skips routing altogether.
"""

from core.features.matching import Option, choose
from core.features.registry import FeatureRegistry
from core.ports import ModelProvider
from core.types import Caller, Feature

INSTRUCTION = "Choose the feature that best matches the staff member's question."


class FeatureRouter:
    def __init__(self, model: ModelProvider, registry: FeatureRegistry, default: str):
        self.model = model
        self.registry = registry
        self.default = default

    async def route(self, caller: Caller, text: str) -> Feature:
        available = self.registry.for_role(caller.role)
        if not available:
            raise LookupError(f"No features for role {caller.role}")
        options = [Option(f.id, f.description) for f in available]
        chosen = await choose(self.model, INSTRUCTION, text, options)
        by_id = {f.id: f for f in available}
        if chosen:
            return by_id[chosen]
        return by_id.get(self.default, available[0])
