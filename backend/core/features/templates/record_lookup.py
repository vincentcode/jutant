"""`record_lookup` template.

Answers a question about one record (a transaction, a product...). The model calls the
pack's lookup tools and restates the fields that answer the question, citing the record.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext, tool_loop


class RecordLookupTemplate:
    id = "record_lookup"
    requires_citation = True

    def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        return tool_loop(ctx)
