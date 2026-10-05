"""Helpers that create indexed `apps.knowledge` documents for tests."""

from django.conf import settings

from apps.knowledge import services
from core.documents.chunking import Chunk


def vector(*hot: int) -> list[float]:
    """An embedding with 1.0 at the given positions, so tests control vector similarity."""
    values = [0.0] * settings.JUTANT_EMBED_DIM
    for i in hot:
        values[i] = 1.0
    return values


def indexed_document(
    title: str,
    chunks: list[tuple[str, str, list[float]]],
    *,
    classification: str = "internal",
    doc_type: str = "policy",
):
    document = services.register_document(
        title=title,
        source_path=f"/docs/{title}.pdf",
        doc_type=doc_type,
        classification=classification,
        checksum=title,
        text=" ".join(c[1] for c in chunks),
    )
    services.replace_chunks(
        document_id=document.id,
        chunks=[Chunk(i, section, text) for i, (section, text, _) in enumerate(chunks)],
        embeddings=[e for _, _, e in chunks],
    )
    return document
