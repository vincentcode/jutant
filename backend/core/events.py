"""Events streamed by `Orchestrator.ask`."""

from dataclasses import dataclass

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


Event = (
    FeatureSelected
    | ToolStarted
    | ToolFinished
    | TextDelta
    | PlaybookStepShown
    | Completed
    | Failed
)
