"""`document_qa` template.

Tool loop over document search; answer only from retrieved text.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext


class DocumentQaTemplate:
    id = "document_qa"
    requires_citation = True

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        raise NotImplementedError
        yield  # pragma: no cover
