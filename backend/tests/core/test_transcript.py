"""Replaying a conversation records each message's route, tools, answer and procedure state."""

from core.evals.transcript import replay
from core.types import ModelReply
from providers.llm.fake import FakeModel
from tests.builders import doc_result, make_rig, teller


async def test_each_message_is_recorded_with_its_route_tools_and_answer() -> None:
    model = FakeModel(
        replies=[
            ModelReply("policy_qa"),  # routing
            ModelReply(None, ()),  # nudged: answers without a tool...
            ModelReply("Both holders need ID."),  # ...then answers
        ]
    )
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})
    transcript = await replay(rig.orchestrator, teller(), ["KYC for joint accounts?"], "X-1")
    [turn] = transcript.turns
    assert (turn.feature, turn.routed_by) == ("policy_qa", "model")
    assert transcript.item_id == "X-1" and turn.procedure is None
    assert rig.orchestrator.audit is rig.audit  # the audit sink is given back


async def test_a_procedure_turn_records_the_step_and_the_state_after() -> None:
    model = FakeModel(
        replies=[ModelReply("troubleshooting"), ModelReply("done")]  # routing; "verified" read
    )  # as the step's answer
    rig = await make_rig(model)
    transcript = await replay(
        rig.orchestrator, teller(), ["card blocked", "customer verified"], "P-1"
    )
    start, answer = transcript.turns
    assert start.steps == ["Blocked card · step 1: Verify"]
    assert answer.routed_by == "procedure" and answer.reply_read_as == "continue (by model)"
    assert answer.procedure == "Blocked card · step 2 (Reason)"
