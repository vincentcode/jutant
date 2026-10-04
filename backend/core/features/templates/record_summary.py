"""`record_summary` template.

One tool call returns an assembled record; the model writes the summary.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext


class RecordSummaryTemplate:
    id = "record_summary"
    requires_citation = True

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        raise NotImplementedError
        yield  # pragma: no cover
