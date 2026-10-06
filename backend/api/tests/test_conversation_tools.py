"""The assistant's name and look, features for the menu, and managing conversations."""

import pytest
from django.test.utils import override_settings

from api.tests.conftest import api, make_staff
from core.types import ModelReply

pytestmark = pytest.mark.django_db(transaction=True)


async def test_the_name_and_accent_are_public_for_the_sign_in_page() -> None:
    with override_settings(JUTANT_THEME_ACCENT="#00664f"):
        async with api() as client:
            response = await client.http.get("/api/app")  # not signed in
    assert response.status_code == 200
    assert response.json() == {"name": "Bank Staff Assistant", "accent": "#00664f"}


async def test_features_come_grouped_with_example_questions() -> None:
    await make_staff("ama")
    async with api() as client:
        await client.login("ama")
        features = {f["id"]: f for f in (await client.http.get("/api/features")).json()}
    assert features["transaction_lookup"]["group"] == "Look something up"
    assert features["troubleshooting"]["group"] == "Step-by-step help"
    assert features["policy_qa"]["examples"] == ["What ID do joint account holders need?"]
    assert "customer_360" not in features  # not a teller's


async def test_conversations_can_be_searched_renamed_and_deleted_by_their_owner() -> None:
    await make_staff("ama")
    await make_staff("kofi")
    async with api(ModelReply("It failed: account closed."), ModelReply("8.5%.")) as client:
        await client.login("ama")
        transfer = await client.conversation()
        await client.ask(transfer, text="Why did TX-0002 fail?", feature_id="transaction_lookup")
        product = await client.conversation()
        await client.ask(product, text="Rate on SAV-STD?", feature_id="product_lookup")

        def ids(response) -> list[str]:
            return [c["id"] for c in response.json()]

        assert ids(await client.http.get("/api/conversations", params={"q": "account closed"})) == [
            transfer
        ]  # found by an answer's words, not just the title

        renamed = await client.http.patch(
            f"/api/conversations/{transfer}", json={"title": "  TX-0002 for Mrs Mensah "}
        )
        assert renamed.json()["title"] == "TX-0002 for Mrs Mensah"
        assert (
            await client.http.patch(f"/api/conversations/{transfer}", json={"title": ""})
        ).status_code == 422

        await client.http.post("/api/auth/logout")
        await client.login("kofi")
        assert (await client.http.delete(f"/api/conversations/{transfer}")).status_code == 404
        assert (
            await client.http.patch(f"/api/conversations/{transfer}", json={"title": "Mine now"})
        ).status_code == 404

        await client.http.post("/api/auth/logout")
        await client.login("ama")
        assert (await client.http.delete(f"/api/conversations/{transfer}")).status_code == 204
        assert ids(await client.http.get("/api/conversations")) == [product]
        assert (await client.http.get(f"/api/conversations/{transfer}/messages")).status_code == 404


async def test_an_image_upload_says_it_was_read_by_ocr() -> None:
    await make_staff("ama")
    async with api() as client:
        await client.login("ama")
        conversation = await client.conversation()
        response = await client.http.post(
            f"/api/conversations/{conversation}/upload",
            files={"file": ("id.png", b"\x89PNG fake", "image/png")},
        )
    assert response.status_code == 201
    assert response.json()["note"] == "read from an image by OCR: check names and numbers"
