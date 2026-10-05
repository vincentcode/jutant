"""`document_extraction` template.

With an uploaded file: pull the fields of one of the pack's extraction schemas (an ID card, a
payslip...), or summarise the file in parts if the question asks for no particular fields.
Without an upload: the tool loop, so the model can fetch an indexed document (a circular) itself.
"""

from collections.abc import AsyncIterator
from typing import Any

from core.documents.chunking import split
from core.documents.summarise import summarise
from core.events import Event, TextDelta
from core.extraction.extractor import extract
from core.features.matching import Option, best_keyword_match, choose, keywords
from core.features.templates.base import FeatureContext, tool_loop

EXTRACT_WORDS = frozenset({"extract", "field", "pull", "detail", "fill", "read"})
CLASSIFY = "Which kind of document is this?"
CLASSIFY_SAMPLE_CHARS = 1500


class DocumentExtractionTemplate:
    id = "document_extraction"
    requires_citation = False

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        if not ctx.upload_text:
            async for event in tool_loop(ctx):
                yield event
            return
        schema_type = await self._schema_for(ctx)
        if schema_type is None:
            yield TextDelta(await summarise(ctx.model, split(ctx.upload_text)))
            return
        fields = ctx.extraction_schemas[schema_type]
        values = await extract(ctx.model, ctx.upload_text, fields)
        yield TextDelta(format_fields(schema_type, values))

    async def _schema_for(self, ctx: FeatureContext) -> str | None:
        """The schema the question names, else one the model picks if fields were asked for."""
        options = [Option(t, t.replace("_", " ")) for t in ctx.extraction_schemas]
        named = best_keyword_match(ctx.question, options)
        if named or not keywords(ctx.question) & EXTRACT_WORDS:
            return named
        return await choose(ctx.model, CLASSIFY, ctx.upload_text[:CLASSIFY_SAMPLE_CHARS], options)


def format_fields(schema_type: str, values: dict[str, Any]) -> str:
    lines = [f"{schema_type.replace('_', ' ').capitalize()}:"]
    for name, value in values.items():
        shown = "not found" if value is None else value
        lines.append(f"- {name.replace('_', ' ').capitalize()}: {shown}")
    return "\n".join(lines)
