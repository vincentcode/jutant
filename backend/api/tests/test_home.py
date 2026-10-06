"""The home screen, the Knowledge panel's documents, and account details for Settings."""

import pytest
from asgiref.sync import sync_to_async

from api.tests.conftest import api, make_staff
from apps.knowledge.tests.factories import indexed_document, vector

pytestmark = pytest.mark.django_db(transaction=True)


async def test_home_shows_only_what_the_role_may_use() -> None:
    await make_staff("ama", role="teller")
    await make_staff("efua", role="customer_service")
    async with api() as client:
        await client.login("ama")
        teller = (await client.http.get("/api/home")).json()
        await client.http.post("/api/auth/logout")
        await client.login("efua")
        service = (await client.http.get("/api/home")).json()

    def features(home: dict, part: str) -> list[str]:
        return [c["feature_id"] for c in home[part]]

    assert "customer_360" not in features(teller, "cards")  # tellers may not use it
    assert "customer_360" in features(service, "cards")
    assert "customer_360" not in features(teller, "quick_actions")
    card = teller["cards"][0]
    assert (card["title"], card["icon"], card["label"]) == (
        "Investigate a transaction",
        "landmark",
        "Payments",
    )


async def test_the_knowledge_panel_lists_only_documents_the_role_may_read() -> None:
    await make_staff("ama", role="teller")
    await sync_to_async(indexed_document)(
        "KYC Policy", [("4.2", "Joint accounts.", vector(0))], doc_type="policy"
    )
    await sync_to_async(indexed_document)(
        "Circular 14/2026", [("Purpose", "Dormant accounts.", vector(1))], doc_type="circular"
    )
    await sync_to_async(indexed_document)(
        "Board minutes", [("1", "Secret.", vector(2))], classification="board_only"
    )
    async with api() as client:
        await client.login("ama")
        everything = (await client.http.get("/api/documents")).json()
        searched = (await client.http.get("/api/documents", params={"q": "kyc"})).json()
        circulars = (await client.http.get("/api/documents", params={"type": "circular"})).json()

    assert sorted(d["title"] for d in everything) == ["Circular 14/2026", "KYC Policy"]
    assert [d["title"] for d in searched] == ["KYC Policy"]
    assert [d["title"] for d in circulars] == ["Circular 14/2026"]
    assert "text" not in everything[0]  # titles only; reading goes through the assistant


async def test_account_details_include_the_branch() -> None:
    await make_staff("ama", branch="ACC-01")
    async with api() as client:
        me = (await client.login("ama")).json()
    assert me["attributes"] == {"branch": "ACC-01"}
