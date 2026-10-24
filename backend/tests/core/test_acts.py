"""Dialogue acts: what a message does to the conversation's subjects, named for every turn, and
decided by a classifier when one is set."""

from core.context import ContextStack
from core.context.acts import ActState, act_of, reading_for
from core.context.reader import Reading
from core.types import ModelReply
from tests.core.test_context import ask, bank, shown


def stack_with_paused_procedure() -> tuple[ContextStack, int, int]:
    stack = ContextStack()
    procedure = stack.push("troubleshooting", procedure=True)
    side = stack.push("policy_qa")
    return stack, procedure.id, side.id


def test_every_reading_is_one_act() -> None:
    stack, procedure, side = stack_with_paused_procedure()
    assert act_of(Reading("new"), stack) == "new"
    assert act_of(Reading("continue", side), stack) == "follow_up"
    assert act_of(Reading("return", procedure), stack) == "resume"
    assert act_of(Reading("stop", procedure), stack) == "stop"
    on_top = ContextStack()
    step = on_top.push("troubleshooting", procedure=True)
    assert act_of(Reading("continue", step.id), on_top) == "answer"
    on_top.push("policy_qa")
    first = on_top.push("product_lookup")
    assert act_of(Reading("return", on_top.frames[1].id), on_top) == "return"
    assert first.id != on_top.frames[1].id


def test_an_act_gives_a_reading_only_where_it_says_which_subject() -> None:
    stack, procedure, side = stack_with_paused_procedure()
    assert reading_for("resume", stack) == Reading("return", procedure, by="classifier")
    assert reading_for("follow_up", stack) == Reading("continue", side, by="classifier")
    assert reading_for("stop", stack) == Reading("stop", procedure, by="classifier")
    assert reading_for("new", stack) == Reading("new", by="classifier")
    assert reading_for("return", stack) is None  # back to which? the model reads it
    assert reading_for("answer", stack) is None  # the step's own reading decides
    assert reading_for("resume", ContextStack()) is None  # nothing to resume


class Acts:
    """A trained act classifier, scripted."""

    def __init__(self, act: str, confidence: float) -> None:
        self.answer = (act, confidence)
        self.states: list[ActState] = []

    async def act(self, text, state):
        self.states.append(state)
        return self.answer


async def test_a_confident_act_classifier_decides_without_the_model() -> None:
    rig, model, conversation = await bank(
        ModelReply("done"),  # step 1 done
        ModelReply("policy_qa"),  # a side question
        ModelReply("Two IDs."),
    )
    await ask(rig, conversation, "card is blocked", "troubleshooting")
    await ask(rig, conversation, "customer verified")
    await ask(rig, conversation, "what ID do joint holders need?")
    rig.orchestrator.act_classifier = acts = Acts("resume", 0.97)
    resumed = await ask(rig, conversation, "carry on")
    assert shown(resumed) == [2] and not model.replies  # no model call for the reading
    assert acts.states[-1].procedure == "Blocked card" and not acts.states[-1].procedure_on_top
    [read] = [e for e in rig.audit.events if e[1] == "turn_read"][-1:]
    assert (read[2]["act"], read[2]["by"]) == ("resume", "classifier")


async def test_an_unsure_act_classifier_leaves_it_to_the_model() -> None:
    rig, model, conversation = await bank(
        ModelReply("done"),
        ModelReply("policy_qa"),
        ModelReply("Two IDs."),
        ModelReply("back"),  # the model's two-way question still decides
    )
    await ask(rig, conversation, "card is blocked", "troubleshooting")
    await ask(rig, conversation, "customer verified")
    await ask(rig, conversation, "what ID do joint holders need?")
    rig.orchestrator.act_classifier = Acts("new", 0.4)
    resumed = await ask(rig, conversation, "carry on")
    assert shown(resumed) == [2] and not model.replies
    [read] = [e for e in rig.audit.events if e[1] == "turn_read"][-1:]
    assert (read[2]["act"], read[2]["by"]) == ("resume", "model:resumes")


async def test_every_turn_records_its_act_and_the_state_it_was_read_in() -> None:
    rig, _, conversation = await bank(ModelReply("done"))
    await ask(rig, conversation, "card is blocked", "troubleshooting")
    await ask(rig, conversation, "customer verified")
    reads = [e[2] for e in rig.audit.events if e[1] == "turn_read"]
    assert [r["act"] for r in reads] == ["new", "answer"]
    assert reads[1]["state"] == {"subject_open": False, "procedure": True, "procedure_on_top": True}
