"""Events streamed by `Orchestrator.ask`."""

from dataclasses import dataclass
from typing import Literal

from core.types import Answer, PlaybookStep, ToolCall, ToolResult


@dataclass(frozen=True)
class FeatureSelected:
    feature_id: str
    switched_from: str | None = None  # the feature staff preferred, if the question was not for it


@dataclass(frozen=True)
class ToolStarted:
    call: ToolCall


@dataclass(frozen=True)
class ToolFinished:
    result: ToolResult


@dataclass(frozen=True)
class TextDelta:
    """Answer text. From a template, `continues` marks a piece of a streamed answer; without it
    the text is a new paragraph. The orchestrator's output already carries the paragraph
    breaks, so whoever reads it only appends."""

    text: str
    continues: bool = False


@dataclass(frozen=True)
class PlaybookStepShown:
    playbook_id: str
    step: PlaybookStep
    playbook_title: str = ""  # for "Failed transfer · step 3"
    answered: str | None = None  # the step was answered from a looked-up record, with this


@dataclass(frozen=True)
class Completed:
    answer: Answer


@dataclass(frozen=True)
class Failed:
    reason: str


@dataclass(frozen=True)
class HandOver:
    """The conversation passes the turn to a feature it chose: the orchestrator answers the
    message with that feature instead. Never streamed to the client."""

    feature_id: str


@dataclass(frozen=True)
class Choice:
    """One thing a message might be, for staff to pick:

    - `answer`: the reply to the step the procedure on top waits on (with its feature);
    - `subject`: about an open subject (`subject_id`, with its feature);
    - `resume`: back to the paused procedure;
    - `feature`: a new subject for a kind of help (`feature_id`);
    - `new`: something else, read afresh.
    """

    kind: Literal["answer", "subject", "resume", "feature", "new"]
    title: str
    subject_id: int | None = None
    feature_id: str | None = None


@dataclass(frozen=True)
class Clarify:
    """The assistant could not tell what the message is: staff pick one of `choices`, and the
    client sends the message again saying which. The question is also the turn's text.
    `reason`: why it asked, for measuring how often it asks and why (`ClarifyReason`)."""

    question: str
    choices: tuple[Choice, ...]
    reason: str = ""


# Why the assistant asked: the reading could not tell what the message is (`unread`), nor whether
# it is about an open subject or another of its kind (`same_or_new`); the conversation model
# named several kinds of help (`ask_which`), made no valid choice (`no_valid_call`), or talked
# with staff, the kinds of help offered with its words (`talk`).
ClarifyReason = Literal["unread", "same_or_new", "ask_which", "no_valid_call", "talk"]


Event = (
    FeatureSelected
    | ToolStarted
    | ToolFinished
    | TextDelta
    | PlaybookStepShown
    | Completed
    | Failed
    | Clarify
    | HandOver
)
