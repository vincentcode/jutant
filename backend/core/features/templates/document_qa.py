"""`document_qa` template.

Answers a question from the pack's documents. The model searches, then answers only from
the retrieved text; an answer without a cited source is replaced by the orchestrator.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext, tool_loop


class DocumentQaTemplate:
    id = "document_qa"
    requires_citation = True

    def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        return tool_loop(ctx)
