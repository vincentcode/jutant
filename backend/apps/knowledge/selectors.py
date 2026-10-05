"""Every read query for knowledge.

`search` runs two searches over the chunks, by meaning (vector distance) and by words
(Postgres full text), and merges them with reciprocal rank fusion: a chunk scores
1 / (60 + rank) in each list it appears in. Every query is filtered to the classifications the
caller may read, and only indexed documents with a label are ever returned.

The word search matches chunks containing any of the question's words, ranked by how many
match, rather than requiring every word: a question rarely uses exactly the document's words.
A search narrowed by document type that finds nothing is retried without the type, because the
model sometimes guesses a type that does not exist.
"""

import re
from uuid import UUID

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F, QuerySet
from pgvector.django import CosineDistance

from apps.knowledge.models import Chunk, Document
from apps.knowledge.services import SEARCH_CONFIG

RRF_K = 60
CANDIDATES_PER_LIST = 4  # each search fetches limit x this many before merging


def searchable_chunks(classifications: list[str], doc_type: str | None = None) -> QuerySet[Chunk]:
    chunks = Chunk.objects.select_related("document").filter(
        document__status=Document.Status.INDEXED,
        document__classification__in=[c for c in classifications if c],
    )
    return chunks.filter(document__doc_type=doc_type) if doc_type else chunks


def search(
    *,
    query: str,
    query_embedding: list[float] | None,
    classifications: list[str],
    limit: int,
    doc_type: str | None = None,
) -> list[tuple[Chunk, float]]:
    """The best `limit` chunks with their fused scores, best first."""
    if not classifications or limit <= 0:
        return []
    results = _search(query, query_embedding, searchable_chunks(classifications, doc_type), limit)
    if not results and doc_type:
        results = _search(query, query_embedding, searchable_chunks(classifications), limit)
    return results


def _search(
    query: str, query_embedding: list[float] | None, base: QuerySet[Chunk], limit: int
) -> list[tuple[Chunk, float]]:
    candidates = limit * CANDIDATES_PER_LIST
    ranked_lists: list[list[Chunk]] = []
    if query_embedding is not None:
        ranked_lists.append(
            list(
                base.exclude(embedding=None)
                .annotate(distance=CosineDistance("embedding", query_embedding))
                .order_by("distance")[:candidates]
            )
        )
    terms = re.findall(r"\w+", query)
    if terms:
        words = SearchQuery(" or ".join(terms), search_type="websearch", config=SEARCH_CONFIG)
        ranked_lists.append(
            list(
                base.filter(search_vector=words)
                .annotate(rank=SearchRank(F("search_vector"), words))
                .order_by("-rank")[:candidates]
            )
        )

    scores: dict[UUID, float] = {}
    chunks: dict[UUID, Chunk] = {}
    for ranked in ranked_lists:
        for position, chunk in enumerate(ranked, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (RRF_K + position)
            chunks[chunk.id] = chunk
    best = sorted(scores, key=scores.__getitem__, reverse=True)[:limit]
    return [(chunks[chunk_id], scores[chunk_id]) for chunk_id in best]


def get_document(*, document_id: UUID, classifications: list[str]) -> Document | None:
    """The document if it is indexed and the caller may read its classification, else None."""
    return Document.objects.filter(
        id=document_id,
        status=Document.Status.INDEXED,
        classification__in=[c for c in classifications if c],
    ).first()


def find_by_checksum(*, checksum: str) -> Document | None:
    return Document.objects.filter(checksum=checksum, status=Document.Status.INDEXED).first()


def indexed_documents() -> list[Document]:
    """Every indexed document, for re-chunking and re-embedding."""
    return list(Document.objects.filter(status=Document.Status.INDEXED).order_by("created_at"))
