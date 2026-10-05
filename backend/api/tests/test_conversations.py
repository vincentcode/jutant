import pytest

from api.tests.conftest import api, make_staff
from core.types import ModelReply, ToolCall

pytestmark = pytest.mark.django_db(transaction=True)


def calls(name: str, **arguments) -> ModelReply:
    return ModelReply(None, (ToolCall("1", name, arguments),))


async def test_features_offered_depend_on_the_role() -> None:
    await make_staff("ama", role="teller")
    await make_staff("efua", role="customer_service")
    async with api() as client:
        await client.login("ama")
        teller = {f["id"] for f in (await client.http.get("/api/features")).json()}
        await client.login("efua")
        service = {f["id"] for f in (await client.http.get("/api/features")).json()}
    assert "customer_360" not in teller
    assert "customer_360" in service
    assert len(teller) == 7


async def test_start_list_and_read_back_a_conversation_with_citations() -> None:
    await make_staff("ama")
    replies = [
        calls("transactions.get_status", reference="TX-0002"),
        ModelReply("TX-0002 failed: the beneficiary account is closed."),
    ]
    async with api(*replies) as client:
        await client.login("ama")
        conversation_id = await client.conversation()
        await client.ask(
            conversation_id, text="Why did TX-0002 fail?", feature_id="transaction_lookup"
        )

        listed = (await client.http.get("/api/conversations")).json()
        history = (await client.http.get(f"/api/conversations/{conversation_id}/messages")).json()

    assert [c["title"] for c in listed] == ["Why did TX-0002 fail?"]
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "Why did TX-0002 fail?"),
        ("assistant", "TX-0002 failed: the beneficiary account is closed."),
    ]
    assert history[1]["feature_id"] == "transaction_lookup"
    assert history[1]["citations"] == [
        {"kind": "record", "title": "Transaction", "locator": "TX-0002"}
    ]


async def test_someone_elses_conversation_is_not_found() -> None:
    await make_staff("ama")
    await make_staff("kojo")
    async with api() as client:
        await client.login("ama")
        conversation_id = await client.conversation()
        await client.login("kojo")
        base = f"/api/conversations/{conversation_id}"
        assert (await client.http.get(f"{base}/messages")).status_code == 404
        assert (await client.http.post(f"{base}/ask", json={"text": "hi"})).status_code == 404
        upload = await client.http.post(f"{base}/upload", files={"file": ("a.txt", b"x")})
        assert upload.status_code == 404
        assert (await client.http.get("/api/conversations")).json() == []


async def test_feature_access_is_refused_before_streaming() -> None:
    await make_staff("ama")
    async with api() as client:
        await client.login("ama")
        conversation_id = await client.conversation()
        url = f"/api/conversations/{conversation_id}/ask"
        restricted = await client.http.post(
            url, json={"text": "C1001", "feature_id": "customer_360"}
        )
        unknown = await client.http.post(url, json={"text": "hi", "feature_id": "nope"})
        empty = await client.http.post(url, json={"text": ""})
    assert restricted.status_code == 403
    assert unknown.status_code == 404
    assert empty.status_code == 422


async def test_not_signed_in_is_401() -> None:
    async with api() as client:
        assert (await client.http.get("/api/conversations")).status_code == 401
        assert (await client.http.post("/api/conversations")).status_code == 401
