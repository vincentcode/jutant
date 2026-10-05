"""`checklist` template.

What a request needs: forms, signatures, approvals. The model calls the pack's requirement
tools and document search, and answers as a list.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext, tool_loop


class ChecklistTemplate:
    id = "checklist"
    requires_citation = True

    def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        return tool_loop(ctx)
