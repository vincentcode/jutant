"""Every write for knowledge. Keyword-only arguments, atomic."""

from datetime import date
from uuid import UUID

from django.contrib.postgres.search import SearchVector
from django.db import transaction

from apps.knowledge.models import Chunk, Document
from core.documents.chunking import Chunk as ChunkData

SEARCH_CONFIG = "english"


@transaction.atomic
def register_document(
    *,
    title: str,
    source_path: str,
    doc_type: str,
    classification: str,
    checksum: str,
    text: str = "",
    version: str = "",
    effective_date: date | None = None,
) -> Document:
    """Record a document as pending. It becomes searchable once its chunks are indexed."""
    return Document.objects.create(
        title=title,
        source_path=source_path,
        doc_type=doc_type,
        classification=classification,
        checksum=checksum,
        text=text,
        version=version,
        effective_date=effective_date,
    )


@transaction.atomic
def replace_chunks(
    *, document_id: UUID, chunks: list[ChunkData], embeddings: list[list[float]]
) -> Document:
    """Replace a document's chunks, build their full-text index, and mark it indexed."""
    if len(chunks) != len(embeddings):
        raise ValueError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")
    document = Document.objects.select_for_update().get(id=document_id)
    Chunk.objects.filter(document=document).delete()
    Chunk.objects.bulk_create(
        Chunk(document=document, order=c.order, section=c.section, text=c.text, embedding=e)
        for c, e in zip(chunks, embeddings, strict=True)
    )
    Chunk.objects.filter(document=document).update(
        search_vector=SearchVector("section", weight="A", config=SEARCH_CONFIG)
        + SearchVector("text", weight="B", config=SEARCH_CONFIG)
    )
    document.status = Document.Status.INDEXED
    document.save(update_fields=["status"])
    return document


@transaction.atomic
def index_document(
    *,
    title: str,
    source_path: str,
    doc_type: str,
    classification: str,
    checksum: str,
    text: str,
    chunks: list[ChunkData],
    embeddings: list[list[float]],
    effective_date: date | None = None,
) -> tuple[Document, bool]:
    """Store a parsed document and its chunks in one transaction, ready for search.

    A file ingested again from the same path replaces the earlier document (its version goes
    up), so an updated policy never sits in the index beside its old text. Returns the
    document and whether it replaced one.
    """
    document = Document.objects.select_for_update().filter(source_path=source_path).first()
    replaced = document is not None
    if document is None:
        document = Document(source_path=source_path)
    else:
        document.version = str(int(document.version) + 1) if document.version.isdigit() else "2"
    document.title = title
    document.doc_type = doc_type
    document.classification = classification
    document.checksum = checksum
    document.text = text
    document.effective_date = effective_date
    document.status = Document.Status.PENDING
    if not document.version:
        document.version = "1"
    document.save()
    return replace_chunks(document_id=document.id, chunks=chunks, embeddings=embeddings), replaced


@transaction.atomic
def mark_failed(*, document_id: UUID) -> None:
    Document.objects.filter(id=document_id).update(status=Document.Status.FAILED)


@transaction.atomic
def set_classification(*, document_id: UUID, label: str) -> Document:
    """Change a document's label. The caller checks the label is one of the pack's."""
    document = Document.objects.select_for_update().get(id=document_id)
    document.classification = label
    document.save(update_fields=["classification"])
    return document
