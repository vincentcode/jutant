from uuid import uuid4

from core.events import Completed, PlaybookStepShown, TextDelta
from core.playbooks.filtering import steps_for
from core.playbooks.runner import FINISHED, STOPPED
from core.types import Caller, ModelReply
from providers.llm.fake import FakeModel
from tests.builders import BLOCKED_CARD, collect_events, make_rig, teller


def shown(events) -> list[int]:
    return [e.step.order for e in events if isinstance(e, PlaybookStepShown)]


def texts(events) -> list[str]:
    return [e.text for e in events if isinstance(e, TextDelta)]


async def start_blocked_card(rig, conversation_id):
    return await collect_events(
        rig.orchestrator.ask(teller(), conversation_id, "card is blocked", "troubleshooting")
    )


def test_audience_filtering() -> None:
    assert [s.order for s in steps_for(BLOCKED_CARD, "staff")] == [1, 2, 3, 4, 5]
    assert [s.order for s in steps_for(BLOCKED_CARD, "customer")] == [3, 5]


async def test_playbook_starts_and_branches_by_choice() -> None:
    rig = await make_rig(FakeModel())  # one playbook: chosen without asking the model
    conversation_id = uuid4()

    first = await start_blocked_card(rig, conversation_id)
    assert shown(first) == [1]
    assert isinstance(first[-1], Completed)

    second = await collect_events(rig.orchestrator.ask(teller(), conversation_id, "done"))
    assert shown(second) == [2]

    third = await collect_events(rig.orchestrator.ask(teller(), conversation_id, "fraud hold"))
    assert shown(third) == [4]  # next_on: fraud_hold -> 4, skipping 3

    run = rig.playbooks.runs[conversation_id]
    assert run.answers == {1: "confirm", 2: "fraud_hold"}
    assert run.feature_id == "troubleshooting"


async def test_none_steps_are_shown_and_the_run_completes() -> None:
    rig = await make_rig(FakeModel())
    conversation_id = uuid4()
    await start_blocked_card(rig, conversation_id)
    await collect_events(rig.orchestrator.ask(teller(), conversation_id, "yes"))
    await collect_events(rig.orchestrator.ask(teller(), conversation_id, "wrong_pin"))

    last = await collect_events(rig.orchestrator.ask(teller(), conversation_id, "done"))

    assert shown(last) == [5]  # step 3 -> next_on confirm -> 5, a "none" step
    assert texts(last) == [FINISHED]
    assert rig.playbooks.runs[conversation_id].status == "completed"


async def test_unrecognised_reply_repeats_the_step() -> None:
    rig = await make_rig(FakeModel())
    conversation_id = uuid4()
    await start_blocked_card(rig, conversation_id)

    events = await collect_events(rig.orchestrator.ask(teller(), conversation_id, "hmm"))

    assert shown(events) == [1]
    assert "done" in texts(events)[0]


async def test_free_text_choice_is_mapped_by_the_model() -> None:
    rig = await make_rig(FakeModel(replies=[ModelReply("wrong_pin")]))
    conversation_id = uuid4()
    await start_blocked_card(rig, conversation_id)
    await collect_events(rig.orchestrator.ask(teller(), conversation_id, "done"))

    events = await collect_events(
        rig.orchestrator.ask(teller(), conversation_id, "they typed the code wrong three times")
    )

    assert shown(events) == [3]


async def test_cancel_abandons_the_run_and_frees_the_conversation() -> None:
    rig = await make_rig(FakeModel())
    conversation_id = uuid4()
    await start_blocked_card(rig, conversation_id)

    events = await collect_events(rig.orchestrator.ask(teller(), conversation_id, "Cancel"))

    assert texts(events) == [STOPPED]
    assert await rig.playbooks.get_run(conversation_id) is None


async def test_choosing_another_feature_leaves_the_playbook() -> None:
    model = FakeModel(replies=[ModelReply("From the policy."), ModelReply("unused")])
    rig = await make_rig(model)
    conversation_id = uuid4()
    await start_blocked_card(rig, conversation_id)

    events = await collect_events(
        rig.orchestrator.ask(teller(), conversation_id, "KYC rule?", "policy_qa")
    )

    assert shown(events) == []  # answered by the chosen feature, not the playbook
    assert rig.playbooks.runs[conversation_id].status == "abandoned"
    assert "playbook_step" in rig.audit.names()


async def test_the_same_feature_keeps_the_playbook_going() -> None:
    rig = await make_rig(FakeModel())
    conversation_id = uuid4()
    await start_blocked_card(rig, conversation_id)
    events = await collect_events(
        rig.orchestrator.ask(teller(), conversation_id, "done", "troubleshooting")
    )
    assert shown(events) == [2]


async def test_customer_audience_sees_only_customer_steps() -> None:
    rig = await make_rig(FakeModel())
    customer = Caller("C1", "teller", "customer", {})
    events = await collect_events(
        rig.orchestrator.ask(customer, uuid4(), "card blocked", "troubleshooting")
    )
    assert shown(events) == [3]


async def test_playbook_steps_are_kept_in_history() -> None:
    rig = await make_rig(FakeModel())
    conversation_id = uuid4()
    await start_blocked_card(rig, conversation_id)
    stored = rig.conversations.messages[conversation_id][-1]
    # Kept as a step, for the client to show as one, and as text for the model's history.
    assert [s.step.order for s in stored.steps] == [1]
    assert stored.steps[0].playbook_title == "Blocked card"
    [as_read] = (await rig.conversations.recent_messages(conversation_id, 6))[-1:]
    assert "Step 1: Verify." in as_read.content
