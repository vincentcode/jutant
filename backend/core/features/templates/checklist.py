"""`checklist` template.

What a request needs: forms, signatures, approvals. The model calls the pack's requirement
tools, and answers as a list. When the feature can search documents, the question is searched
first, in code: requirement records exist only for the request types the pack lists, so a
request without one (or a requirement written only in a policy) is still answered from the
documents, instead of the model inventing a request type that is not found.
"""

from collections.abc import AsyncIterator
from uuid import uuid4

from core.documents.tools import SEARCH_TOOL
from core.events import Event
from core.features.templates.base import FeatureContext, tool_loop
from core.types import ToolCall


class ChecklistTemplate:
    id = "checklist"
    requires_citation = True

    def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        searches = (
            [ToolCall(f"search_{uuid4().hex[:8]}", SEARCH_TOOL, {"query": ctx.lookup})]
            if SEARCH_TOOL in ctx.feature.tools
            else []
        )
        return tool_loop(ctx, searches)
