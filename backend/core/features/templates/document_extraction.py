"""`document_extraction` template.

With an uploaded file: pull the fields of one of the pack's extraction schemas (an ID card, a
payslip...), or summarise the file if the question asks for no particular fields.

Without an upload: summarise an indexed document (a circular). The document is found and read
in code: the question is searched, and every part of the best match is fetched, so the summary
covers the whole document rather than the sections a search happened to return. The answer
names the document, so staff can see which one was summarised. If the feature lacks the
documents tools, the model works with whatever tools it has, in the tool loop.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from core.documents.summarise import summarise
from core.documents.tools import GET_TOOL, SEARCH_TOOL
from core.events import Event, TextDelta
from core.extraction.extractor import extract
from core.features.matching import Option, best_keyword_match, choose, keywords
from core.features.templates.base import FeatureContext, run_call, tool_loop
from core.types import ToolCall

EXTRACT_WORDS = frozenset({"extract", "field", "pull", "detail", "fill", "read"})
CLASSIFY = "Which kind of document is this?"
CLASSIFY_SAMPLE_CHARS = 1500
MAX_PARTS = 8  # about 100,000 characters; beyond that, staff are told the summary is partial
NOT_FOUND = "I could not find a document matching that. Try its title or reference number."
UNREADABLE = "I found the document but could not read it. Please try again or open it directly."


class DocumentExtractionTemplate:
    id = "document_extraction"
    requires_citation = False

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        if not ctx.upload_text:
            reads_in_code = {SEARCH_TOOL, GET_TOOL} <= set(ctx.feature.tools)
            async for event in summarise_indexed(ctx) if reads_in_code else tool_loop(ctx):
                yield event
            return
        schema_type = await self._schema_for(ctx)
        if schema_type is None:
            yield TextDelta(await summarise(ctx.model, ctx.upload_text))
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


async def summarise_indexed(ctx: FeatureContext) -> AsyncIterator[Event]:
    search = ToolCall(_call_id(), SEARCH_TOOL, {"query": ctx.question})
    async for event in run_call(ctx, search):
        yield event
    found = ctx.results[-1]
    hits = found.data if found.ok and isinstance(found.data, list) else []
    if not hits:
        yield TextDelta(NOT_FOUND)
        return

    document_id, title = str(hits[0]["document_id"]), str(hits[0]["title"])
    texts: list[str] = []
    part, parts = 1, 1
    while part <= min(parts, MAX_PARTS):
        fetch = ToolCall(_call_id(), GET_TOOL, {"document_id": document_id, "part": part})
        async for event in run_call(ctx, fetch):
            yield event
        result = ctx.results[-1]
        if not result.ok or not isinstance(result.data, dict):
            break
        texts.append(str(result.data.get("text", "")))
        parts = int(result.data.get("parts", 1))
        part += 1
    if not texts:
        yield TextDelta(UNREADABLE)
        return

    summary = await summarise(ctx.model, "".join(texts))
    note = ""
    if len(texts) < parts:
        note = (
            f"\n\nThis covers the first {len(texts)} of {parts} parts of the document; "
            "open it for the rest."
        )
    yield TextDelta(f"Summary of {title}:\n\n{summary}{note}")


def _call_id() -> str:
    return f"read_{uuid4().hex[:8]}"


def format_fields(schema_type: str, values: dict[str, Any]) -> str:
    """The fields as a table (Markdown, which the client renders), a missing one marked
    *not found* rather than guessed."""
    lines = [
        f"**{schema_type.replace('_', ' ').capitalize()}**",
        "",
        "| Field | Value |",
        "| --- | --- |",
    ]
    for name, value in values.items():
        shown = "*not found*" if value in (None, "") else _cell(str(value))
        lines.append(f"| {name.replace('_', ' ').capitalize()} | {shown} |")
    return "\n".join(lines)


def _cell(value: str) -> str:
    """A value safe inside a table cell: one line, no column breaks."""
    return " ".join(value.split()).replace("|", "\\|")
