"""Protocols the core depends on. Django apps and providers implement them."""

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from core.types import (
    Caller,
    Citation,
    DocumentHit,
    DocumentText,
    Feature,
    Message,
    ModelReply,
    Playbook,
    PlaybookRunState,
    ToolCall,
    ToolResult,
    ToolSpec,
)

if TYPE_CHECKING:
    from core.actions.types import Proposal, ProposalStatus
    from core.context.acts import Act, ActState
    from core.events import PlaybookStepShown

AUDIT_EVENTS = (
    "question_asked",
    "feature_routed",
    "tool_called",
    "tool_denied",
    "tool_failed",
    "answer_returned",
    "playbook_started",
    "playbook_step",
    "document_uploaded",
    "feedback_given",
    "conversation_deleted",
    "turn_read",  # what a message did to the conversation's context, and what decided it
    "action_proposed",
    "action_confirmed",
    "action_failed",
    "action_cancelled",
)


class ModelProvider(Protocol):
    async def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ModelReply: ...

    def stream_chat(
        self, messages: list[Message], tools: list[ToolSpec]
    ) -> AsyncIterator[str | ModelReply]:
        """Like `chat`, but yields the reply's text in pieces as it is written, then the whole
        ModelReply last. A reply that calls tools yields no text, only the ModelReply."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class IntentClassifier(Protocol):
    """Which kind of help a question is for, by its words alone: the router's step between
    patterns and the model. Comparing with each feature's examples by meaning is the default
    (`core.features.meaning`); a trained classifier (Rasa NLU, or one trained on embeddings) can
    take its place in `providers/`."""

    async def scores(
        self, text: str, features: Sequence[Feature], model: "ModelProvider | None" = None
    ) -> list[tuple[float, Feature]]:
        """Each of `features` with how close `text` is to it (0 to 1, higher is closer),
        closest first; empty when it cannot tell (nothing to compare with, or its own model
        cannot be reached). `model`: the turn's model (traced and timed), for a classifier
        that uses the platform's own; others ignore it. The router decides with its own
        thresholds, set for the classifier in use."""
        ...


class DialogueActClassifier(Protocol):
    """How a message relates to the conversation (`core.context.acts`), from its words and the
    conversation's state: trained on the acts the audit log records for every turn. Consulted
    after the code rules and before the model's questions; a confident act decides."""

    async def act(self, text: str, state: "ActState") -> "tuple[Act, float] | None":
        """The act and how sure (0 to 1); None if it cannot tell."""
        ...


class ToolClient(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...
    async def call(
        self, caller: Caller, call: ToolCall, trace_context: Mapping[str, str] | None = None
    ) -> ToolResult:
        """`trace_context` (a tracing carrier) lets the server join the caller's trace."""
        ...


class ConversationStore(Protocol):
    async def create(self, caller: Caller) -> UUID: ...
    async def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]: ...
    async def append(
        self,
        conversation_id: UUID,
        message: Message,
        feature_id: str | None = None,
        citations: tuple[Citation, ...] = (),
        steps: tuple["PlaybookStepShown", ...] = (),
        trace_context: Mapping[str, str] | None = None,
    ) -> None:
        """`steps` are the playbook steps the turn showed. They are kept as steps, and read
        back by `recent_messages` as part of the message's text. `trace_context` is the
        turn's trace, so feedback on the answer can be attached to it."""
        ...

    async def context(self, conversation_id: UUID) -> dict[str, Any]:
        """What staff are talking about, as kept after the last turn (empty at first)."""
        ...

    async def save_context(self, conversation_id: UUID, context: dict[str, Any]) -> None: ...


class PlaybookStore(Protocol):
    async def get(self, playbook_id: str) -> Playbook: ...
    async def list(self) -> list[Playbook]: ...
    async def get_run(self, conversation_id: UUID) -> PlaybookRunState | None: ...
    async def save_run(self, conversation_id: UUID, state: PlaybookRunState) -> None: ...


class DocumentStore(Protocol):
    """`pack`: only that pack's documents and those every pack shares; "" for all."""

    async def search(
        self,
        query: str,
        classifications: list[str],
        limit: int,
        doc_type: str | None = None,
        pack: str = "",
    ) -> list[DocumentHit]: ...
    async def get_document(
        self, document_id: UUID, classifications: list[str], pack: str = ""
    ) -> DocumentText: ...


class AuditSink(Protocol):
    async def record(self, caller: Caller, event: str, detail: dict[str, Any]) -> None: ...


class IdentityProvider(Protocol):
    async def caller_for(self, user_id: str) -> Caller: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class ActionStore(Protocol):
    """Proposed actions. `claim` and `cancel` change a proposal only if it belongs to the caller
    and is still waiting, atomically: two clicks on Send confirm it once. Both raise
    `ActionUnavailable` otherwise; a proposal past its time is marked expired first."""

    async def create(self, proposal: "Proposal") -> None: ...
    async def claim(self, proposal_id: UUID, caller_id: str, now: datetime) -> "Proposal": ...
    async def finish(
        self,
        proposal_id: UUID,
        status: "ProposalStatus",
        reference: str = "",
        outcome: str = "",
    ) -> "Proposal": ...
    async def cancel(self, proposal_id: UUID, caller_id: str, now: datetime) -> "Proposal": ...
    async def for_conversation(self, conversation_id: UUID, caller_id: str) -> list["Proposal"]: ...
