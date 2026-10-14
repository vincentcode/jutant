"""Frozen dataclasses shared across the core. No behaviour beyond small helpers."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class PackRole:
    """What a person is in one pack: their role there, and that pack's attributes (a branch)."""

    role: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Caller:
    """Who is asking. With several packs loaded, a person has a role in each pack they may use
    (`packs`); `in_pack` gives the caller as one pack sees them, and that is what its tools and
    rules receive. A caller without `packs` is the same in every pack (one pack loaded, tests).
    """

    id: str  # staff id from the directory
    role: str  # one of the pack's roles
    audience: str  # "staff" in the first release
    attributes: dict[str, Any] = field(default_factory=dict)  # caller attributes from the pack
    pack: str = ""  # the pack this caller acts in, once `in_pack` chose it
    packs: dict[str, PackRole] = field(default_factory=dict)  # pack name -> role there

    def in_pack(self, pack: str) -> "Caller | None":
        """The caller as `pack` sees them: their role and attributes there. None if they have no
        role in it. Unchanged when the caller has no roles by pack, or `pack` is the
        deployment's own (""), as its conversation is."""
        if not self.packs or not pack:
            return self
        found = self.packs.get(pack)
        if found is None:
            return None
        return replace(self, role=found.role, attributes=dict(found.attributes), pack=pack)


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
    feature_id: str | None = None  # an answer's: the feature that gave it
    citations: tuple["Citation", ...] = ()  # an answer's sources


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
    prompt_tokens: int | None = None  # as the model reports them, for tracing
    completion_tokens: int | None = None


@dataclass(frozen=True)
class ArgumentSource:
    """Where a prefetched tool call takes one argument from. Exactly one is set."""

    question: bool = False  # the whole question
    match: str | None = None  # a regular expression: its first group (or the whole match)
    value: Any = None  # a fixed value
    entity: str | None = None  # the conversation's current entity of this type (a transfer)
    # The values it can take, as (value, what it means): the model picks one for the question,
    # or none, and the call is made in code (a request type: joint_account_opening).
    choose: tuple[tuple[str, str], ...] = ()
    detail: str | None = None  # one of the feature's details (`Detail`), once staff gave it
    optional: bool = False  # left out of the call when it has no value, instead of no call


@dataclass(frozen=True)
class EntityType:
    """A kind of thing staff talk about, declared by the pack (a transfer, a product), and how
    to recognise one in text: `pattern` matches its id (first group, or the whole match)."""

    name: str
    pattern: str
    words: tuple[str, ...] = ()  # what staff call it: "transfer", "payment"
    # In a tool result, the field holding one's name ("Standard Savings" for SAV-STD), so a
    # later message using the name points to it.
    name_field: str | None = None


@dataclass(frozen=True)
class Detail:
    """Something a feature must know before it looks anything up (`core.features.needs`).
    Found by an entity type's pattern, picked from listed values, a date or a period: exactly
    one."""

    name: str
    label: str  # what it is, in staff's words, for asking: "the customer's phone number"
    entity: str | None = None  # the entity type whose id it is
    # The values staff pick from, as (value, title): a message gives one by naming it (its
    # title, its id or one of its `words`), else staff are asked with the titles as buttons.
    choose: tuple[tuple[str, str], ...] = ()
    words: tuple[tuple[str, tuple[str, ...]], ...] = ()  # value -> other words naming it
    date: bool = False  # a date, read in code
    ask: str = ""  # the question asking for it alone (a choice: "Which ... was it?")
    title: str = ""  # its name on a button ("Phone number"); else from its label
    # A period, read in code: "10 to 14 November", or one day. Kept as "start/end" (ISO).
    period: bool = False
    nearest: bool = False  # a date or period given without a year is the one nearest today


@dataclass(frozen=True)
class Needs:
    """Which details a feature needs: `first`, asked one at a time, then any one complete set of
    `one_of`. With `by`, the sets depend on that detail's value (`one_of_by`), falling back to
    `one_of` for a value not listed."""

    first: tuple[str, ...] = ()
    one_of: tuple[tuple[str, ...], ...] = ()
    by: str | None = None
    one_of_by: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = ()

    def sets_for(self, known: Mapping[str, str]) -> tuple[tuple[str, ...], ...]:
        """The sets that apply, given the details `known`."""
        if self.by is not None and (value := known.get(self.by)) is not None:
            return dict(self.one_of_by).get(value, self.one_of)
        return self.one_of


@dataclass(frozen=True)
class Prefetch:
    """A tool call made in code before the model is asked, when every argument can be filled
    from the question. It saves the model a step it would take anyway."""

    tool: str
    arguments: dict[str, ArgumentSource]
    # What a question is about for this call to be the one it needs: of a feature's calls with
    # a `when`, the model picks the one (or none) a question needs, and only that one is made.
    when: str = ""


@dataclass(frozen=True)
class Feature:
    id: str
    template: str  # one of the platform's template ids
    title: str
    description: str  # used by the router
    prompt: str  # resolved prompt text
    tools: tuple[str, ...]  # tool names this feature may use
    roles: tuple[str, ...]  # roles allowed to use the feature; empty = all
    route_patterns: tuple[str, ...] = ()  # a match routes here without asking the model
    route_examples: tuple[str, ...] = ()  # questions this feature answers, matched by meaning
    prefetch: tuple[Prefetch, ...] = ()
    suggestions: tuple[str, ...] = ()  # questions offered on the client's first screen
    # Asked when the question gives none of what the prefetch calls need (a reference, a
    # customer number), instead of calling the model, which can only fail to find a source.
    ask_for: str = ""
    # Where follow-ups to this feature's answers go, if not to itself (after a summary, to the
    # feature that answers questions about documents).
    follow_ups: str = ""
    # What it must know before looking anything up, asked for in code when missing.
    details: tuple[Detail, ...] = ()
    needs: Needs | None = None
    pack: str = ""  # the pack it comes from; "" for the deployment's own (its conversation)

    def allows(self, role: str) -> bool:
        return not self.roles or role in self.roles

    def allows_caller(self, caller: Caller) -> bool:
        """Whether `caller` may use it: they have a role in its pack that it allows."""
        found = caller.in_pack(self.pack)
        return found is not None and self.allows(found.role)


@dataclass(frozen=True)
class StepLookup:
    """A record a step fetches with the staff member's reply: a transfer by its reference."""

    tool: str
    argument: str  # the tool argument the reply fills
    pattern: str | None = None  # the reply must contain it; its first group (or match) is used


@dataclass(frozen=True)
class PlaybookStep:
    order: int
    title: str
    instruction: str  # may quote a looked-up record: {1.failure_reason}
    audience: tuple[str, ...]  # e.g. ("staff",) or ("staff", "customer")
    expects: Literal["confirm", "choice", "text", "none"] = "confirm"
    choices: tuple[str, ...] = ()
    next_on: dict[str, int] = field(default_factory=dict)  # choice -> step order
    lookup: StepLookup | None = None
    answer_from: str | None = None  # "1.status": a looked-up field that answers this choice


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
    facts: dict[int, dict[str, Any]] = field(default_factory=dict)  # step order -> record
    paused: bool = False  # staff asked something else; the run waits on its step until resumed


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
