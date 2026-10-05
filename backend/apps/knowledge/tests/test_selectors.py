import pytest

from apps.knowledge import selectors, services
from apps.knowledge.models import Document
from apps.knowledge.tests.factories import indexed_document, vector

pytestmark = pytest.mark.django_db


def titles(results) -> list[str]:
    return [f"{chunk.document.title} {chunk.section}" for chunk, _ in results]


def test_full_text_search_finds_words_and_stems() -> None:
    indexed_document(
        "KYC Policy",
        [("4.2 Joint accounts", "Both holders must provide identification.", vector(0))],
    )
    indexed_document("Fees", [("1 Charges", "Monthly maintenance charges.", vector(1))])
    results = selectors.search(
        query="joint account holder", query_embedding=None, classifications=["internal"], limit=4
    )
    assert titles(results) == ["KYC Policy 4.2 Joint accounts"]


def test_vector_and_text_results_are_fused() -> None:
    indexed_document("A", [("1", "dormant reactivation form", vector(0))])
    indexed_document("B", [("1", "unrelated wording", vector(1, 2))])
    indexed_document("C", [("Dormant reactivation", "dormant reactivation steps", vector(1))])
    results = selectors.search(
        query="dormant reactivation",
        query_embedding=vector(1),
        classifications=["internal"],
        limit=3,
    )
    # C is first in both lists (heading match, closest vector), so it wins. A is found by
    # words only and B by meaning only, but both still make the merged list.
    assert titles(results)[0] == "C Dormant reactivation"
    assert set(titles(results)) == {"A 1", "B 1", "C Dormant reactivation"}


def test_search_only_returns_readable_classifications() -> None:
    indexed_document("Public rates", [("1", "savings rates", vector(0))], classification="public")
    indexed_document(
        "Internal rates", [("1", "savings rates", vector(0))], classification="internal"
    )
    results = selectors.search(
        query="savings rates", query_embedding=vector(0), classifications=["public"], limit=4
    )
    assert titles(results) == ["Public rates 1"]
    assert (
        selectors.search(query="savings", query_embedding=vector(0), classifications=[], limit=4)
        == []
    )


def test_unindexed_and_unlabelled_documents_are_not_searchable() -> None:
    services.register_document(
        title="Pending", source_path="p", doc_type="policy", classification="internal", checksum="p"
    )
    indexed_document("Unlabelled", [("1", "savings rates", vector(0))], classification="")
    results = selectors.search(
        query="savings", query_embedding=vector(0), classifications=["internal", ""], limit=4
    )
    assert results == []


def test_doc_type_filter() -> None:
    indexed_document("Circular", [("1", "fees change", vector(0))], doc_type="circular")
    indexed_document("Policy", [("1", "fees change", vector(0))], doc_type="policy")
    results = selectors.search(
        query="fees",
        query_embedding=vector(0),
        classifications=["internal"],
        limit=4,
        doc_type="circular",
    )
    assert titles(results) == ["Circular 1"]


def test_reindexing_replaces_chunks() -> None:
    document = indexed_document("KYC", [("1", "old text", vector(0))])
    from core.documents.chunking import Chunk

    services.replace_chunks(
        document_id=document.id, chunks=[Chunk(0, "1", "new text")], embeddings=[vector(0)]
    )
    assert [c.text for c in document.chunks.all()] == ["new text"]
    assert Document.objects.get(id=document.id).status == Document.Status.INDEXED


def test_get_document_respects_classification() -> None:
    document = indexed_document("Medical", [("1", "x", vector(0))], classification="medical")
    assert selectors.get_document(document_id=document.id, classifications=["internal"]) is None
    assert selectors.get_document(document_id=document.id, classifications=["medical"]) == document
