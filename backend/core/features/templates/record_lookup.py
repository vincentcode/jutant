"""`record_lookup` template.

Tool loop over pack lookup tools; answer restates record fields.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext


class RecordLookupTemplate:
    id = "record_lookup"
    requires_citation = True

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        raise NotImplementedError
        yield  # pragma: no cover
