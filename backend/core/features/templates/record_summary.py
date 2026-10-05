"""`record_summary` template.

A one-screen brief of a record. One tool call returns the record already assembled, with
every figure computed in code; the model only writes the prose around it.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext, tool_loop


class RecordSummaryTemplate:
    id = "record_summary"
    requires_citation = True

    def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        return tool_loop(ctx)
