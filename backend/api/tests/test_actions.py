"""Sending a proposed request over the API: a card the assistant showed, sent by its owner
only, once. The banking pack declares no actions, so the runtime is given one with a fake
system behind it."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from api.sse import to_frame
from api.tests.conftest import api, make_staff
from apps.actions.adapters import DjangoActionStore
from core.actions.service import ActionService
from core.actions.types import Action, Draft, Field, Proposal
from core.events import ActionProposed
from core.types import ToolResult
from providers.mcp.fake import FakeToolClient
from tests.fakes import InMemoryAudit

pytestmark = pytest.mark.django_db(transaction=True)

LEAVE = Action("leave_request", "Leave request", "leave.propose", "leave.submit")
DRAFT = Draft("Annual leave, 10-14 Nov", (Field("Days", "5"),), {"type": "annual"})


async def with_actions(client, result: ToolResult):
    tools = FakeToolClient({"leave.submit": result})
    client.runtime.actions = ActionService(
        [LEAVE], DjangoActionStore(), tools, client.runtime.conversations, InMemoryAudit()
    )
    return tools


async def proposed(client, conversation_id: str, username: str):
    caller = await client.runtime.identity.caller_for(username)
    return await client.runtime.actions.propose(caller, UUID(conversation_id), LEAVE, DRAFT)


async def test_a_card_is_listed_sent_once_and_its_outcome_kept() -> None:
    await make_staff("ama")
    async with api() as client:
        await client.login("ama")
        tools = await with_actions(
            client, ToolResult("", ok=True, data={"reference": "LV-7", "status": "Waiting"})
        )
        conversation = await client.conversation()
        card = await proposed(client, conversation, "ama")

        listed = (await client.http.get(f"/api/conversations/{conversation}/actions")).json()
        assert [(c["title"], c["status"], c["fields"]) for c in listed] == [
            ("Leave request", "proposed", [{"label": "Days", "value": "5"}])
        ]
        assert "submit" not in listed[0]  # the system's arguments stay on the server

        url = f"/api/conversations/{conversation}/actions/{card.id}/confirm"
        sent = await client.http.post(url)
        assert sent.status_code == 200, sent.text
        assert (sent.json()["status"], sent.json()["reference"]) == ("sent", "LV-7")
        again = await client.http.post(url)
        assert again.status_code == 409 and "already been sent" in again.json()["detail"]
        assert len(tools.calls) == 1


async def test_another_persons_card_does_not_exist_for_them() -> None:
    await make_staff("ama")
    await make_staff("kofi")
    async with api() as client:
        await client.login("ama")
        await with_actions(client, ToolResult("", ok=True, data={}))
        conversation = await client.conversation()
        card = await proposed(client, conversation, "ama")
        await client.login("kofi")
        for verb in ("confirm", "cancel"):
            response = await client.http.post(
                f"/api/conversations/{conversation}/actions/{card.id}/{verb}"
            )
            assert response.status_code == 404
        missing = f"/api/conversations/{conversation}/actions/{uuid4()}/confirm"
        assert (await client.http.post(missing)).status_code == 404


async def test_a_card_can_be_cancelled_and_then_not_sent() -> None:
    await make_staff("ama")
    async with api() as client:
        await client.login("ama")
        tools = await with_actions(client, ToolResult("", ok=True, data={}))
        conversation = await client.conversation()
        card = await proposed(client, conversation, "ama")
        base = f"/api/conversations/{conversation}/actions/{card.id}"
        assert (await client.http.post(f"{base}/cancel")).json()["status"] == "cancelled"
        assert (await client.http.post(f"{base}/confirm")).status_code == 409
        assert tools.calls == []


def test_the_card_event_carries_what_it_shows_and_not_what_it_sends() -> None:
    card = Proposal(
        uuid4(),
        "leave_request",
        "Leave request",
        "calendar",
        uuid4(),
        "E1",
        DRAFT,
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    text = to_frame(ActionProposed(card))
    assert text.startswith("event: action_proposed\n")
    assert '"summary": "Annual leave, 10-14 Nov"' in text and 'annual"}' not in text
