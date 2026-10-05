"""Turns document files into searchable chunks: parse, OCR, chunk, embed, index.

1. Checksum the file; skip it if an indexed document already has the same content.
2. Parse it to text by file type. PDF pages with no text layer go through OCR.
3. Split the text into chunks that keep their section headings.
4. Embed the chunks in batches through the model provider.
5. Store the document and its chunks in one transaction. A file ingested again from the same
   path replaces the earlier version.

A document is searchable only once indexed, and only by roles that may read its label.
"""

import asyncio
import hashlib
import logging
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from asgiref.sync import sync_to_async

from apps.knowledge import selectors, services
from core.documents.chunking import Chunk, split
from core.ports import ModelProvider
from ingestion.parsers import docx, pdf, text
from providers.ocr.base import OcrEngine

logger = logging.getLogger(__name__)

SUPPORTED = (*text.SUFFIXES, *docx.SUFFIXES, *pdf.SUFFIXES)
EMBED_BATCH = 16


class IngestError(Exception):
    """The file cannot be ingested; the message says why in plain language."""


@dataclass(frozen=True)
class IngestResult:
    path: Path
    status: Literal["indexed", "replaced", "skipped"]
    document_id: UUID
    chunks: int = 0
    note: str = ""


class Ingestor:
    def __init__(
        self,
        model: ModelProvider,
        labels: Collection[str],
        embed_dim: int,
        ocr: OcrEngine | None = None,
        batch_size: int = EMBED_BATCH,
        document_prefix: str = "",
    ):
        self.model = model
        self.labels = frozenset(labels)  # the classification labels the pack defines
        self.embed_dim = embed_dim
        self.ocr = ocr
        self.batch_size = batch_size
        self.document_prefix = document_prefix  # the embedding model's prefix for documents

    async def ingest(
        self, path: Path, *, doc_type: str, classification: str, title: str | None = None
    ) -> IngestResult:
        if classification not in self.labels:
            raise IngestError(
                f"{classification!r} is not a label of this pack ({', '.join(sorted(self.labels))})"
            )
        checksum, source_path = await asyncio.to_thread(_fingerprint, path)
        existing = await sync_to_async(selectors.find_by_checksum)(checksum=checksum)
        if existing is not None:
            return IngestResult(path, "skipped", existing.id, note="same content already indexed")

        body, note = await asyncio.to_thread(self._parse, path)  # OCR can take a while
        chunks = split(body)
        if not chunks:
            raise IngestError(f"{path.name}: no text found{f' ({note})' if note else ''}")
        embeddings = await self.embed([self._embedding_text(c) for c in chunks])

        document, replaced = await sync_to_async(services.index_document)(
            title=title or _title(path),
            source_path=source_path,
            doc_type=doc_type,
            classification=classification,
            checksum=checksum,
            text=body,
            chunks=chunks,
            embeddings=embeddings,
        )
        status = "replaced" if replaced else "indexed"
        return IngestResult(path, status, document.id, len(chunks), note)

    async def reindex(self) -> int:
        """Re-chunk and re-embed every indexed document from its stored text.

        For after a change of chunking or embedding model; the original files are not needed.
        Returns the number of documents re-indexed.
        """
        documents = await sync_to_async(selectors.indexed_documents)()
        for document in documents:
            chunks = split(document.text)
            embeddings = await self.embed([self._embedding_text(c) for c in chunks])
            await sync_to_async(services.replace_chunks)(
                document_id=document.id, chunks=chunks, embeddings=embeddings
            )
        return len(documents)

    def _embedding_text(self, chunk: Chunk) -> str:
        """What is embedded for a chunk: its heading and text, so the heading's meaning counts."""
        body = f"{chunk.section}\n{chunk.text}" if chunk.section else chunk.text
        return self.document_prefix + body

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = await self.model.embed(texts[start : start + self.batch_size])
            for vector in batch:
                if len(vector) != self.embed_dim:
                    raise IngestError(
                        f"the embedding model returns {len(vector)} dimensions but the index "
                        f"expects {self.embed_dim}; check JUTANT_EMBED_MODEL and JUTANT_EMBED_DIM"
                    )
            vectors.extend(batch)
        return vectors

    def _parse(self, path: Path) -> tuple[str, str]:
        """The document's text, and a note about anything that could not be read."""
        suffix = path.suffix.lower()
        if suffix in text.SUFFIXES:
            return text.parse(path), ""
        if suffix in docx.SUFFIXES:
            return docx.parse(path), ""
        if suffix in pdf.SUFFIXES:
            parsed = pdf.parse(path, self.ocr)
            notes = []
            if parsed.ocr_pages:
                notes.append(f"{parsed.ocr_pages} of {parsed.pages} pages read by OCR")
            if parsed.unreadable_pages:
                reason = "" if self.ocr else "; OCR is not available"
                notes.append(f"{parsed.unreadable_pages} pages unreadable{reason}")
            return parsed.text, ", ".join(notes)
        raise IngestError(f"{path.name}: unsupported file type (use {', '.join(SUPPORTED)})")


def _fingerprint(path: Path) -> tuple[str, str]:
    """The file's content hash, and its absolute path (which identifies a document over time)."""
    return hashlib.sha256(path.read_bytes()).hexdigest(), str(path.resolve())


def _title(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").strip().capitalize()
