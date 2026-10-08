"""Reading a turn: what the message does to the stack.

- `continue`: about a frame already open (for a procedure: the reply to its step). The frame
  comes to the top.
- `return`: back to an earlier frame. For a procedure: show its step again.
- `new`: a new subject, for a feature (or for the router to choose).
- `stop`: end the procedure.

Certain cases are decided without the model (`certain`): staff said what the message is (a step
answer clicked on its card, Resume, Stop, "a new question"), staff locked a feature, there is no
frame yet, or the message names an entity already in a frame (or a new one). Everything else is
read by the model (`read`), with the stack in view: one call, its reply checked against the
options, asked once more if not; if still unclear, the caller decides what to do.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from core.context.stack import ContextStack, Frame
from core.features.matching import Option, ask_model
from core.ports import ModelProvider
from core.types import Feature, PlaybookStep

Action = Literal["continue", "return", "new", "stop"]
# What staff say a message is, so it is not read: a step answer clicked on its card, the answer
# to "is that your answer or a new question?" or "is this about X, or something new?", the
# paused procedure's Resume and Stop, a subject chip clicked to return to it, or a kind of help
# picked to start (`start`, with the feature: the message is its title, not a question).
ReplyAs = Literal["answer", "question", "resume", "stop", "return", "continue", "start"]

INSTRUCTION = (
    "A staff member is working with an assistant. Their open subjects, most recent first:\n"
    "{subjects}\n\nWhat is their new message? Choose one."
)
CONFIRMED = "confirm"  # what a confirm step records
SAME_INSTRUCTION = (
    "A staff member was talking about: {subject}.\nIs their new message about that same one, "
    "or about a different one of the same kind? Choose one."
)
ATTEMPTS = 2


@dataclass(frozen=True)
class Reading:
    action: Action
    frame_id: int | None = None
    feature_id: str | None = None  # new: the feature, or None for the router to choose
    choice: str | None = None  # continue on a procedure step: the option, or "confirm"
    by: str = "model"  # what decided: staff, locked, first, entity or model


def certain(
    stack: ContextStack,
    text: str,
    mentioned: Mapping[str, str],
    reply_as: ReplyAs | None,
    locked_feature: str | None,
    subject_id: int | None = None,
    step: PlaybookStep | None = None,
) -> Reading | None:
    """The reading, when it does not need the model; else None. `subject_id`: the subject staff
    clicked (to return to it, or to say a message is about it); `step`: the step the top
    procedure waits on, if any."""
    top, procedure = stack.top, stack.procedure_frame()
    if reply_as == "return" and subject_id is not None and stack.get(subject_id) is not None:
        return Reading("return", subject_id, by="staff")
    if reply_as == "continue" and subject_id is not None and stack.get(subject_id) is not None:
        return Reading("continue", subject_id, by="staff")
    if procedure is not None and reply_as == "stop":
        return Reading("stop", procedure.id, by="staff")
    if procedure is not None and reply_as == "answer":
        return Reading("continue", procedure.id, by="staff")
    if procedure is not None and reply_as == "resume":
        return Reading("return", procedure.id, by="staff")
    if reply_as == "question":
        return Reading("new", feature_id=locked_feature, by="staff")
    if top is None:
        return Reading("new", feature_id=locked_feature, by="first")
    if locked_feature:
        if top.feature_id == locked_feature and top.procedure:
            return None  # the procedure's own feature: a reply to its step, read it
        if top.feature_id == locked_feature:
            return Reading("continue", top.id, by="locked")
        return Reading("new", feature_id=locked_feature, by="locked")
    if top.procedure and step is not None and _takes(step, text):
        return Reading("continue", top.id, by="step")
    if top.procedure or not mentioned:
        return None  # a reply to a step, or a message naming nothing: read it
    if any(top.entities.get(kind) == value for kind, value in mentioned.items()):
        return Reading("continue", top.id, by="entity")
    for kind, value in mentioned.items():
        if (earlier := stack.holding(kind, value)) is not None:
            return Reading("return", earlier.id, by="entity")
    return Reading("new", by="entity")  # a new entity: the router finds its feature


def _takes(step: PlaybookStep, text: str) -> bool:
    """The step looks a record up by a pattern, and the message has one: it is the answer."""
    return bool(step.lookup and step.lookup.pattern and re.search(step.lookup.pattern, text))


async def same_subject(model: ModelProvider, text: str, subject: str) -> bool | None:
    """Whether `text` is about `subject` (True) or another of the same kind (False); None if
    the model could not tell. Asked when the turn's reading chose a feature an open subject
    already has: "how much is the fee?" (the same product) or "and the Standard Savings rate?"
    (another one). A two-way choice a small model makes far more reliably than the full reading."""
    options = [
        Option("same", f"about {subject}"),
        Option("different", "about a different one"),
    ]
    instruction = SAME_INSTRUCTION.format(subject=subject)
    for _ in range(ATTEMPTS):
        chosen = await ask_model(model, instruction, text, options)
        if chosen is not None:
            return chosen == "same"
    return None


async def read(
    model: ModelProvider,
    text: str,
    stack: ContextStack,
    describe: Callable[[Frame], str],
    features: Sequence[Feature],
    step: PlaybookStep | None = None,
) -> Reading | None:
    """What the model reads `text` as, given the stack; None if it could not tell.
    `describe` names a frame in a few words; `step` is the step the top procedure waits on."""
    top = stack.top
    assert top is not None
    options, readings = _options(stack, features, step)
    subjects = "\n".join(f"{n}. {describe(f)}" for n, f in enumerate(stack.frames[:4], 1))
    instruction = INSTRUCTION.format(subjects=subjects)
    for _ in range(ATTEMPTS):
        chosen = await ask_model(model, instruction, text, options)
        if chosen is not None:
            return readings[chosen]
    return None


def _options(
    stack: ContextStack, features: Sequence[Feature], step: PlaybookStep | None
) -> tuple[list[Option], dict[str, Reading]]:
    top = stack.top
    assert top is not None
    options: list[Option] = []
    readings: dict[str, Reading] = {}

    def add(option: Option, reading: Reading) -> None:
        if option.id not in readings:
            options.append(option)
            readings[option.id] = reading

    if top.procedure and step is not None:
        if step.expects == "choice":
            for choice in step.choices:
                words = choice.replace("_", " ")
                add(
                    Option(choice, f"they answer step {step.order}: {words}"),
                    Reading("continue", top.id, choice=choice),
                )
        elif step.expects == "confirm":
            add(
                Option("done", f"they say step {step.order} is done"),
                Reading("continue", top.id, choice=CONFIRMED),
            )
        else:
            add(
                Option("answer", f"they give what step {step.order} asks for"),
                Reading("continue", top.id),
            )
    else:
        add(Option("continue", "more about subject 1, the same thing"), Reading("continue", top.id))
    for number, frame in enumerate(stack.frames[1:4], 2):
        add(Option(f"back_{number}", f"back to subject {number}"), Reading("return", frame.id))
    if not features:  # the feature is chosen later (agent mode): only that it is new
        add(Option("new", "a different subject from these"), Reading("new"))
    for feature in features:
        # Always a new subject, even for subject 1's feature: "and the Standard Savings rate?"
        # after Business Current is a new product, and must not take Business Current's code.
        add(
            Option(feature.id, f"a different subject: {feature.description}"),
            Reading("new", feature_id=feature.id),
        )
    if (procedure := stack.procedure_frame()) is not None:
        add(Option("stop", "they want to stop the procedure"), Reading("stop", procedure.id))
    return options, readings
