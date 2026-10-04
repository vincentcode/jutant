"""`document_extraction` template.

OCR if needed, then schema extraction or chunked summarisation.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext


class DocumentExtractionTemplate:
    id = "document_extraction"
    requires_citation = False

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        raise NotImplementedError
        yield  # pragma: no cover
