"""Protocols the core depends on. Django apps and providers implement them."""

from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from core.types import (
    Caller,
    Citation,
    DocumentHit,
    DocumentText,
    Message,
    ModelReply,
    Playbook,
    PlaybookRunState,
    ToolCall,
    ToolResult,
    ToolSpec,
)

if TYPE_CHECKING:
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
    async def search(
        self, query: str, classifications: list[str], limit: int, doc_type: str | None = None
    ) -> list[DocumentHit]: ...
    async def get_document(self, document_id: UUID, classifications: list[str]) -> DocumentText: ...


class AuditSink(Protocol):
    async def record(self, caller: Caller, event: str, detail: dict[str, Any]) -> None: ...


class IdentityProvider(Protocol):
    async def caller_for(self, user_id: str) -> Caller: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
