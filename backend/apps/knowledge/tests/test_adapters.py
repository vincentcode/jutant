import pytest
from asgiref.sync import sync_to_async

from apps.knowledge.adapters import DjangoDocumentStore
from apps.knowledge.tests.factories import indexed_document, vector

pytestmark = pytest.mark.django_db(transaction=True)


class OneHotEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector(0) for _ in texts]


async def test_search_returns_core_hits() -> None:
    await sync_to_async(indexed_document)(
        "KYC Policy", [("4.2 Joint accounts", "Both holders.", vector(0))]
    )
    hits = await DjangoDocumentStore(OneHotEmbedder()).search("joint holders", ["internal"], 4)
    assert [(h.title, h.section, h.classification) for h in hits] == [
        ("KYC Policy", "4.2 Joint accounts", "internal")
    ]
    assert hits[0].score > 0


async def test_get_document_refuses_unreadable_documents() -> None:
    document = await sync_to_async(indexed_document)(
        "Medical", [("1", "Report.", vector(0))], classification="medical"
    )
    store = DjangoDocumentStore(None)
    found = await store.get_document(document.id, ["medical"])
    assert (found.title, found.classification, found.text) == ("Medical", "medical", "Report.")
    with pytest.raises(KeyError):
        await store.get_document(document.id, ["internal"])
