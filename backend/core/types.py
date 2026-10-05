"""Frozen dataclasses shared across the core. No behaviour beyond small helpers."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class Caller:
    id: str  # staff id from the directory
    role: str  # one of the pack's roles
    audience: str  # "staff" in the first release
    attributes: dict[str, Any] = field(default_factory=dict)  # caller attributes from the pack


@dataclass(frozen=True)
class ToolSpec:
    name: str  # "<server>.<tool>", e.g. "documents.search"
    description: str
    input_schema: dict[str, Any]  # JSON schema


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    created_at: datetime | None = None


@dataclass(frozen=True)
class Citation:
    kind: Literal["document", "record"]
    title: str  # document title or record type
    locator: str  # section, page, or record reference


ToolError = Literal["denied", "invalid_arguments", "not_found", "upstream_error"]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    ok: bool
    data: dict[str, Any] | list[Any] | None = None
    citations: tuple[Citation, ...] = ()
    error: ToolError | None = None


@dataclass(frozen=True)
class ModelReply:
    text: str | None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ArgumentSource:
    """Where a prefetched tool call takes one argument from. Exactly one is set."""

    question: bool = False  # the whole question
    match: str | None = None  # a regular expression: its first group (or the whole match)
    value: Any = None  # a fixed value


@dataclass(frozen=True)
class Prefetch:
    """A tool call made in code before the model is asked, when every argument can be filled
    from the question. It saves the model a step it would take anyway."""

    tool: str
    arguments: dict[str, ArgumentSource]


@dataclass(frozen=True)
class Feature:
    id: str
    template: str  # one of the six template ids
    title: str
    description: str  # used by the router
    prompt: str  # resolved prompt text
    tools: tuple[str, ...]  # tool names this feature may use
    roles: tuple[str, ...]  # roles allowed to use the feature; empty = all
    route_patterns: tuple[str, ...] = ()  # a match routes here without asking the model
    route_examples: tuple[str, ...] = ()  # questions this feature answers, matched by meaning
    prefetch: tuple[Prefetch, ...] = ()

    def allows(self, role: str) -> bool:
        return not self.roles or role in self.roles


@dataclass(frozen=True)
class PlaybookStep:
    order: int
    title: str
    instruction: str
    audience: tuple[str, ...]  # e.g. ("staff",) or ("staff", "customer")
    expects: Literal["confirm", "choice", "text", "none"] = "confirm"
    choices: tuple[str, ...] = ()
    next_on: dict[str, int] = field(default_factory=dict)  # choice -> step order


@dataclass(frozen=True)
class Playbook:
    id: str
    title: str
    description: str
    steps: tuple[PlaybookStep, ...]


PlaybookRunStatus = Literal["active", "completed", "abandoned"]


@dataclass(frozen=True)
class PlaybookRunState:
    playbook_id: str
    current_order: int
    answers: dict[int, str] = field(default_factory=dict)
    status: PlaybookRunStatus = "active"
    feature_id: str = ""  # the feature that started the run, for history and audit


@dataclass(frozen=True)
class DocumentHit:
    document_id: UUID
    title: str
    section: str
    text: str
    score: float
    classification: str


@dataclass(frozen=True)
class DocumentText:
    document_id: UUID
    title: str
    classification: str
    text: str


@dataclass(frozen=True)
class Answer:
    text: str
    feature_id: str
    citations: tuple[Citation, ...]
    tool_calls: tuple[ToolCall, ...]
