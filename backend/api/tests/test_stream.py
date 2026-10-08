import asyncio

import pytest
from asgiref.sync import sync_to_async
from django.core.management import call_command

from api import sse
from api.queue import GenerationQueue
from api.tests.conftest import api, make_staff
from core.events import Completed, TextDelta
from core.types import Answer, ModelReply, ToolCall

pytestmark = pytest.mark.django_db(transaction=True)


def calls(name: str, **arguments) -> ModelReply:
    return ModelReply(None, (ToolCall("1", name, arguments),))


async def test_a_turn_streams_every_event_in_order() -> None:
    await make_staff("ama")
    # The reference is in the question, so the status lookup is made in code (prefetch), then
    # the failure code it points to is looked up in the documents (a second round), and the
    # model only writes the answer, which streams once the turn has a source.
    async with api(ModelReply("It failed: beneficiary account closed.")) as client:
        await client.login("ama")
        events = await client.ask(
            await client.conversation(),
            text="Why did TX-0002 fail?",
            feature_id="transaction_lookup",
        )

    names = [name for name, _ in events]
    assert names[:5] == ["feature_selected", *["tool_started", "tool_finished"] * 2]
    assert events[3][1]["call"]["name"] == "documents.search"  # the code E51, explained
    assert names[-1] == "completed"
    assert set(names[5:-1]) == {"text_delta"} and len(names[5:-1]) > 1  # streamed in pieces
    streamed = "".join(data["text"] for name, data in events if name == "text_delta")
    assert streamed == "It failed: beneficiary account closed."
    assert events[1][1]["label"] == "the transfer"  # in staff's words, from the pack
    finished = events[2][1]["result"]
    assert finished["ok"] and "data" not in finished  # raw tool data stays on the server
    completed = events[-1][1]["answer"]
    assert completed["text"] == streamed
    assert completed["citations"] == [
        {"kind": "record", "title": "Transaction", "locator": "TX-0002"}
    ]


async def test_routed_playbook_streams_its_step() -> None:
    await make_staff("ama")
    await sync_to_async(call_command)("load_pack_playbooks")
    async with api(ModelReply("troubleshooting"), ModelReply("blocked_card")) as client:
        await client.login("ama")
        conversation = await client.conversation()
        events = await client.ask(conversation, text="The card is blocked")
        history = (await client.http.get(f"/api/conversations/{conversation}/messages")).json()
    step = next(data for name, data in events if name == "playbook_step")
    assert step["playbook_id"] == "blocked_card" and step["playbook_title"] == "Blocked card"
    assert step["step"]["order"] == 1 and step["step"]["expects"] == "confirm"
    # The history keeps it as a step, for the client to show as a card after a reload.
    [kept] = history[-1]["steps"]
    assert (kept["title"], kept["playbook_title"], kept["answered"]) == (
        "Verify the customer",
        "Blocked card",
        None,
    )


async def test_upload_then_extract_fields() -> None:
    await make_staff("ama")
    reply = ModelReply('{"full_name": "AMA MENSAH", "id_number": "GHA-123456789-0"}')
    async with api(reply) as client:
        await client.login("ama")
        conversation_id = await client.conversation()
        uploaded = await client.http.post(
            f"/api/conversations/{conversation_id}/upload",
            files={"file": ("id.png", b"\x89PNG fake image", "image/png")},
        )
        assert uploaded.status_code == 201
        upload = uploaded.json()
        assert upload["filename"] == "id.png" and upload["characters"] > 0

        events = await client.ask(
            conversation_id,
            text="Extract the ID card fields",
            feature_id="document_summary_extraction",
            upload_id=upload["upload_id"],
        )
    text = events[-1][1]["answer"]["text"]
    assert "| Full name | AMA MENSAH |" in text
    assert "| Expiry date | *not found* |" in text


async def test_unreadable_uploads_and_unknown_upload_ids() -> None:
    await make_staff("ama")
    async with api() as client:
        await client.login("ama")
        conversation_id = await client.conversation()
        url = f"/api/conversations/{conversation_id}"
        bad = await client.http.post(f"{url}/upload", files={"file": ("a.xls", b"x")})
        assert bad.status_code == 422 and "unsupported file type" in bad.json()["detail"]
        missing = await client.http.post(
            f"{url}/ask",
            json={"text": "x", "upload_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert missing.status_code == 404


async def test_model_outage_ends_the_stream_with_failed() -> None:
    await make_staff("ama")
    async with api() as client:  # no scripted replies: the fake model raises
        await client.login("ama")
        events = await client.ask(await client.conversation(), text="kyc?", feature_id="policy_qa")
    assert events[-1] == ("failed", {"reason": "error"})


async def test_health_reports_each_dependency() -> None:
    async with api() as client:
        response = await client.http.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "database": True,
        "model": True,
        "mcp_servers": {"documents": True, "transactions": True, "services": True},
    }


# --- queue, keep-alive and disconnects, without HTTP ---------------------------


async def answer(text: str = "Done."):
    yield TextDelta(text)
    yield Completed(Answer(text, "f", (), ()))


async def test_a_waiting_request_is_told_its_place() -> None:
    queue = GenerationQueue(1)
    async with queue.slot():  # someone else is generating
        stream = sse.stream(queue, answer)
        first = await anext(stream)
        assert first.startswith("event: queued") and '"position": 1' in first
        pending = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0.05)
        assert not pending.done()  # still waiting for the slot
    assert (await pending).startswith("event: text_delta")


async def test_keep_alive_is_sent_while_generation_is_silent() -> None:
    async def slow():
        await asyncio.sleep(0.25)
        yield TextDelta("late")

    chunks = [c async for c in sse.stream(GenerationQueue(1), slow, keepalive_s=0.05)]
    assert chunks[0] == sse.KEEPALIVE
    assert chunks[-1].startswith("event: text_delta")


async def test_disconnect_cancels_generation_and_frees_the_slot() -> None:
    cancelled = asyncio.Event()

    async def endless():
        try:
            while True:
                yield TextDelta("more")
                await asyncio.sleep(0.01)
        finally:
            cancelled.set()

    queue = GenerationQueue(1)
    stream = sse.stream(queue, endless)
    await anext(stream)
    assert queue.busy
    await stream.aclose()  # what the server does when the client goes away
    await asyncio.wait_for(cancelled.wait(), 1)
    assert not queue.busy


async def test_a_procedure_reads_replies_pauses_for_questions_and_stops_when_asked() -> None:
    await make_staff("ama")
    await sync_to_async(call_command)("load_pack_playbooks")
    replies = [
        ModelReply("troubleshooting"),  # routing: the model chooses
        ModelReply("blocked_card"),  # which procedure
        ModelReply("done"),  # "done" read as the step's answer
        ModelReply("hmm"),  # "blue" cannot be read...
        ModelReply("hmm"),  # ...even asked again
        ModelReply("It failed: beneficiary account closed."),
    ]
    async with api(*replies) as client:
        await client.login("ama")
        conversation = await client.conversation()
        procedure = f"/api/conversations/{conversation}/procedure"
        await client.ask(conversation, text="The card is blocked")
        await client.ask(conversation, text="done")
        assert (await client.http.get(procedure)).json()["step_order"] == 2

        unclear = await client.ask(conversation, text="blue")
        [asked] = [data for name, data in unclear if name == "clarify"]
        assert asked["choices"][0] == {
            "kind": "answer",
            "title": "My answer to step 2: Find the block reason",
            "subject_id": None,
            "feature_id": "troubleshooting",
        }

        await client.ask(
            conversation,
            text="Why did TX-0002 fail?",
            feature_id="transaction_lookup",
            reply_as="question",
        )
        waiting = (await client.http.get(procedure)).json()
        assert waiting == {
            "playbook_id": "blocked_card",
            "playbook_title": "Blocked card",
            "step_order": 2,
            "step_title": "Find the block reason",
            "paused": True,
        }

        stopped = await client.ask(conversation, text="Stop the procedure", reply_as="stop")
        assert ("text_delta", {"text": "Stopped the Blocked card procedure."}) in stopped
        assert (await client.http.get(procedure)).json() is None
