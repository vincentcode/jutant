"""Events streamed by `Orchestrator.ask`."""

from dataclasses import dataclass

from core.types import Answer, PlaybookStep, ToolCall, ToolResult


@dataclass(frozen=True)
class FeatureSelected:
    feature_id: str


@dataclass(frozen=True)
class ToolStarted:
    call: ToolCall


@dataclass(frozen=True)
class ToolFinished:
    result: ToolResult


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class PlaybookStepShown:
    playbook_id: str
    step: PlaybookStep


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
