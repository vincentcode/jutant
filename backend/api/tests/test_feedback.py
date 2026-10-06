"""Rating answers: stored, changeable, private, audited, and passed on to the tracing backend."""

import pytest
from asgiref.sync import sync_to_async

from api.tests.conftest import api, make_staff
from apps.audit import selectors as audit
from core.types import ModelReply

pytestmark = pytest.mark.django_db(transaction=True)


class RecordingSink:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, trace_context, **rating) -> None:
        self.sent.append({"trace": dict(trace_context), **rating})


async def answered(client) -> tuple[str, list[dict]]:
    """A conversation with one answer, and its history."""
    conversation = await client.conversation()
    await client.ask(conversation, text="Why did TX-0002 fail?", feature_id="transaction_lookup")
    history = (await client.http.get(f"/api/conversations/{conversation}/messages")).json()
    return conversation, history


def url(conversation: str, message: str) -> str:
    return f"/api/conversations/{conversation}/messages/{message}/feedback"


async def test_staff_rate_an_answer_and_can_change_their_mind() -> None:
    await make_staff("ama", staff_number="S0042")
    async with api(ModelReply("It failed: the beneficiary account is closed.")) as client:
        sink = RecordingSink()
        client.runtime.feedback = sink
        await client.login("ama")
        conversation, history = await answered(client)
        answer = history[-1]
        assert answer["role"] == "assistant" and answer["feedback"] is None

        down = await client.http.put(
            url(conversation, answer["id"]),
            json={"rating": "down", "reason": "wrong_source", "comment": "Cites the wrong code"},
        )
        assert down.status_code == 200
        assert down.json() == {
            "rating": "down",
            "reason": "wrong_source",
            "comment": "Cites the wrong code",
        }

        up = await client.http.put(url(conversation, answer["id"]), json={"rating": "up"})
        assert up.json() == {"rating": "up", "reason": None, "comment": ""}  # one rating each
        history = (await client.http.get(f"/api/conversations/{conversation}/messages")).json()

    assert history[-1]["feedback"] == {"rating": "up", "reason": None, "comment": ""}
    assert [s["rating"] for s in sink.sent] == ["down", "up"]  # to the answer's trace
    assert sink.sent[0] | {"trace": None} == {
        "trace": None,
        "staff_id": "S0042",
        "rating": "down",
        "reason": "wrong_source",
        "comment": "Cites the wrong code",
        "feature_id": "transaction_lookup",
    }
    events = await sync_to_async(audit.events_for_conversation)(conversation_id=conversation)
    ratings = [e.detail for e in events if e.event == "feedback_given"]
    assert sorted(e["rating"] for e in ratings) == ["down", "up"]


async def test_only_answers_in_your_own_conversations_can_be_rated() -> None:
    await make_staff("ama")
    await make_staff("kofi", staff_number="S0077")
    async with api(ModelReply("Closed account.")) as client:
        await client.login("ama")
        conversation, history = await answered(client)
        question, answer = history[0], history[-1]

        not_an_answer = await client.http.put(
            url(conversation, question["id"]), json={"rating": "up"}
        )
        assert not_an_answer.status_code == 404

        await client.http.post("/api/auth/logout")
        await client.login("kofi")
        someone_else = await client.http.put(
            url(conversation, answer["id"]), json={"rating": "down"}
        )
        assert someone_else.status_code == 404


async def test_a_rating_must_be_up_or_down_with_a_known_reason() -> None:
    await make_staff("ama")
    async with api(ModelReply("Closed account.")) as client:
        await client.login("ama")
        conversation, history = await answered(client)
        bad = await client.http.put(url(conversation, history[-1]["id"]), json={"rating": "meh"})
        odd = await client.http.put(
            url(conversation, history[-1]["id"]), json={"rating": "down", "reason": "rude"}
        )
    assert bad.status_code == 422 and odd.status_code == 422
