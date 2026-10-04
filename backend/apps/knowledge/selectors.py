"""Every read query for knowledge.

`search` merges vector and full-text results by reciprocal rank fusion and is always filtered by
`classification__in`. Only indexed, classified documents are searchable.
"""

from uuid import UUID

from apps.knowledge.models import Chunk


def search(
    *, query: str, query_embedding: list[float], classifications: list[str], limit: int
) -> list[tuple[Chunk, float]]:
    raise NotImplementedError


def get_text(*, document_id: UUID, classifications: list[str]) -> str:
    raise NotImplementedError
