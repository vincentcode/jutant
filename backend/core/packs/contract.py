"""Checks every pack must pass. Returns violations; empty means the pack passes.

- every tool named in a feature exists in the tool specs;
- every tool exposed by a pack server has a policy rule;
- every feature, classification and field-rule role is in `roles`;
- every playbook step has at least one audience, each in `audiences`;
- every `next_on` target is an existing step order;
- `default_feature` exists;
- every prompt file exists and is non-empty;
- every `document_extraction` feature has at least one extraction schema;
- at least one eval question per feature.
"""

from core.packs.loader import Pack
from core.types import ToolSpec


def check(pack: Pack, tool_specs: list[ToolSpec]) -> list[str]:
    raise NotImplementedError
