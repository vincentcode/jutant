"""Implements core.ports.DocumentStore on the knowledge tables."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from asgiref.sync import sync_to_async

from apps.knowledge import selectors
from core.ports import ModelProvider
from core.types import DocumentHit, DocumentText


class DjangoDocumentStore:
    def __init__(self, model: ModelProvider | None, query_prefix: str = ""):
        self.model = model  # embeds the query; None searches by words only
        self.query_prefix = query_prefix  # the embedding model's prefix for queries

    async def search(
        self, query: str, classifications: list[str], limit: int, doc_type: str | None = None
    ) -> list[DocumentHit]:
        embedding = (await self.model.embed([self.query_prefix + query]))[0] if self.model else None
        results = await sync_to_async(selectors.search)(
            query=query,
            query_embedding=embedding,
            classifications=classifications,
            limit=limit,
            doc_type=doc_type,
        )
        return [
            DocumentHit(
                document_id=chunk.document_id,
                title=chunk.document.title,
                section=chunk.section,
                text=chunk.text,
                score=score,
                classification=chunk.document.classification,
            )
            for chunk, score in results
        ]

    async def get_document(self, document_id: UUID, classifications: list[str]) -> DocumentText:
        """Raises KeyError if the document is missing or the caller may not read it."""
        document = await sync_to_async(selectors.get_document)(
            document_id=document_id, classifications=classifications
        )
        if document is None:
            raise KeyError(str(document_id))
        return DocumentText(document.id, document.title, document.classification, document.text)


@dataclass(frozen=True)
class LibraryEntry:
    id: UUID
    title: str
    doc_type: str
    effective_date: date | None
    indexed_at: datetime


class DocumentLibrary:
    """The documents staff may browse in the Knowledge panel."""

    async def list(
        self, classifications: list[str], search: str = "", doc_type: str = ""
    ) -> list[LibraryEntry]:
        rows = await sync_to_async(selectors.library)(
            classifications=classifications, search=search, doc_type=doc_type
        )
        return [
            LibraryEntry(r.id, r.title, r.doc_type, r.effective_date, r.created_at) for r in rows
        ]
