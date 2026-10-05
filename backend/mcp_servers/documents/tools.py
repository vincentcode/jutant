"""The generic documents tools, shipped with the platform for every pack.

- `documents.search`: the sections that best match a question, each cited by title and section.
- `documents.get`: one whole document, for summarising.

Search is always limited to the classifications the caller's role may read; the labels come
from the pack's manifest. A document the caller may not read behaves as if it did not exist.
"""

import math
from collections.abc import Callable
from uuid import UUID

from core.policy.engine import PolicyEngine
from core.ports import DocumentStore
from core.types import Caller, Citation
from mcp_servers.common.guard import GuardedServer, ToolInputError, ToolOutput

MIN_RESULTS = 3  # a small model often asks for one result and misses the section it needed
MAX_RESULTS = 8
# A whole document can be far longer than a small model's context, so it is returned in parts
# of this many characters: `part` 1, 2... up to `parts`.
PART_CHARS = 12_000
WHOLE_DOCUMENT = "whole document"


def create_server(
    store: DocumentStore,
    engine: PolicyEngine,
    secret: str,
    readable: Callable[[str], list[str]],
) -> GuardedServer:
    """`readable(role)` gives the document labels a role may read."""
    server = GuardedServer("documents", engine, secret)

    @server.tool(
        "search",
        "Search the organisation's documents (policies, procedures, circulars). "
        "Returns the best-matching sections with their document title and section.",
    )
    async def search(
        caller: Caller, query: str, doc_type: str | None = None, limit: int = 4
    ) -> ToolOutput:
        limit = max(MIN_RESULTS, min(limit, MAX_RESULTS))
        hits = await store.search(query, readable(caller.role), limit, doc_type)
        return ToolOutput(
            data=[
                {
                    "document_id": str(h.document_id),
                    "title": h.title,
                    "section": h.section,
                    "text": h.text,
                }
                for h in hits
            ],
            citations=tuple(
                Citation("document", h.title, h.section or WHOLE_DOCUMENT) for h in hits
            ),
        )

    @server.tool(
        "get",
        "Get the full text of one document by its document_id, for summarising. A long document "
        "comes in parts: the result says how many; ask for the next with part=2 and so on.",
    )
    async def get(caller: Caller, document_id: str, part: int = 1) -> ToolOutput:
        try:
            uid = UUID(document_id)
        except ValueError:
            raise LookupError(document_id) from None
        document = await store.get_document(uid, readable(caller.role))
        parts = max(1, math.ceil(len(document.text) / PART_CHARS))
        if not 1 <= part <= parts:
            raise ToolInputError(f"part must be between 1 and {parts}")
        start = (part - 1) * PART_CHARS
        return ToolOutput(
            data={
                "document_id": str(document.document_id),
                "title": document.title,
                "text": document.text[start : start + PART_CHARS],
                "part": part,
                "parts": parts,
            },
            citations=(Citation("document", document.title, WHOLE_DOCUMENT),),
        )

    return server
