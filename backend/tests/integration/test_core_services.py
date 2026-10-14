"""The core banking services end to end over the API: account services, loans and deposits,
and card lookup, each on the fake bank, the record fetched in code and set out as facts."""

from typing import Any

import pytest

from api.tests.conftest import api, make_staff
from core.types import ModelReply

pytestmark = pytest.mark.django_db(transaction=True)


def answer(events: list[tuple[str, Any]]) -> dict[str, Any]:
    return next(data for name, data in events if name == "completed")["answer"]


def tools_used(events: list[tuple[str, Any]]) -> list[str]:
    return [data["call"]["name"] for name, data in events if name == "tool_started"]


async def test_account_services_looks_up_the_record_the_question_is_about() -> None:
    await make_staff("ama")
    # The model picks which of the account's records (1: its status), then the field.
    replies = [ModelReply("1"), ModelReply("overview"), ModelReply("A hold of 500.00 is on it.")]
    async with api(*replies) as client:
        await client.login("ama")
        events = await client.ask(
            await client.conversation(),
            text="Why can't money leave account 0011223344?",
            feature_id="account_services",
        )
    assert tools_used(events) == ["accounts.get_status"]
    assert answer(events)["text"] == "A hold of 500.00 is on it."
    assert {"kind": "record", "title": "Account", "locator": "0011223344"} in answer(events)[
        "citations"
    ]


async def test_loans_are_for_roles_that_serve_lending() -> None:
    await make_staff("efua", role="customer_service")
    await make_staff("ama")  # a teller
    replies = [ModelReply("overview"), ModelReply("LN-1001 is in arrears.")]
    async with api(*replies) as client:
        await client.login("efua")
        events = await client.ask(
            await client.conversation(), text="Is loan LN-1001 in arrears?", feature_id=None
        )
        assert tools_used(events) == ["lending.get_loan"]
        assert answer(events)["feature_id"] == "loans_and_deposits"
        await client.login("ama")
        features = {f["id"] for f in (await client.http.get("/api/features")).json()}
    assert "loans_and_deposits" not in features


async def test_card_lookup_reads_the_card_by_its_id() -> None:
    await make_staff("ama")
    replies = [ModelReply("overview"), ModelReply("CRD-3001 was declined abroad (57).")]
    async with api(*replies) as client:
        await client.login("ama")
        events = await client.ask(
            await client.conversation(),
            text="Why was card CRD-3001 declined?",
            feature_id="card_lookup",
        )
    assert tools_used(events)[0] == "cards.get_card"
    assert answer(events)["text"] == "CRD-3001 was declined abroad (57)."
