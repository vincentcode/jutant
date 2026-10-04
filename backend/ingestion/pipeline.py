"""parse -> OCR -> chunk -> embed -> index.

1. Checksum; skip if an indexed document has the same checksum.
2. Parse by file type; OCR PDF pages that have no text layer.
3. `core.documents.chunking.split`.
4. Embed chunks in batches through `ModelProvider.embed`.
5. `knowledge.services.register_document` and `replace_chunks` in one transaction.
"""

from pathlib import Path


def ingest(path: Path, *, doc_type: str, classification: str) -> None:
    raise NotImplementedError
