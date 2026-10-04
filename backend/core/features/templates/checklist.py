"""`checklist` template.

Tool loop over documents and pack requirement tools; returns a list.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext


class ChecklistTemplate:
    id = "checklist"
    requires_citation = True

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        raise NotImplementedError
        yield  # pragma: no cover
