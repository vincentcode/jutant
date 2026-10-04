"""Every write for knowledge. Keyword-only arguments, atomic."""

from datetime import date
from uuid import UUID

from django.db import transaction

from apps.knowledge.models import Document
from core.documents.chunking import Chunk as ChunkData


@transaction.atomic
def register_document(
    *,
    title: str,
    source_path: str,
    doc_type: str,
    classification: str,
    checksum: str,
    version: str = "",
    effective_date: date | None = None,
) -> Document:
    raise NotImplementedError


@transaction.atomic
def replace_chunks(
    *, document_id: UUID, chunks: list[ChunkData], embeddings: list[list[float]]
) -> None:
    """Replace a document's chunks and mark it indexed."""
    raise NotImplementedError


@transaction.atomic
def set_classification(*, document_id: UUID, label: str) -> Document:
    raise NotImplementedError
