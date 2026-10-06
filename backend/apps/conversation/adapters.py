"""Implements core.ports.ConversationStore on the conversation tables, plus the reads and
upload storage the API needs (the API reaches data through adapters, never the ORM)."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async

from apps.conversation import selectors, services
from apps.conversation.models import Conversation as ConversationRow
from apps.conversation.models import Message as MessageRow
from core.events import PlaybookStepShown
from core.playbooks.history import as_text, from_record, to_record
from core.types import Caller, Citation, Message, ToolCall

# Only what staff see in their history; tool calls and results stay internal.
VISIBLE_ROLES = ("user", "assistant")


@dataclass(frozen=True)
class ConversationSummary:
    id: UUID
    title: str
    updated_at: datetime


@dataclass(frozen=True)
class HistoryMessage:
    id: UUID
    role: str
    content: str
    feature_id: str | None
    citations: tuple[Citation, ...]
    created_at: datetime
    steps: tuple[PlaybookStepShown, ...] = ()
    feedback: "Rating | None" = None  # the reader's own rating of an answer


@dataclass(frozen=True)
class Rating:
    rating: str
    reason: str
    comment: str


@dataclass(frozen=True)
class RatedAnswer:
    """What feedback on an answer needs to reach its trace."""

    message_id: UUID
    feature_id: str | None
    trace_context: dict[str, str]
    rating: Rating


class DjangoConversationStore:
    async def create(self, caller: Caller) -> UUID:
        conversation = await sync_to_async(services.start_conversation)(staff_id=caller.id)
        return conversation.id

    async def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]:
        rows = await sync_to_async(selectors.recent_messages)(
            conversation_id=conversation_id, limit=limit
        )
        return [to_message(row) for row in rows]

    async def append(
        self,
        conversation_id: UUID,
        message: Message,
        feature_id: str | None = None,
        citations: tuple[Citation, ...] = (),
        steps: tuple[PlaybookStepShown, ...] = (),
        trace_context: Mapping[str, str] | None = None,
    ) -> None:
        await sync_to_async(services.add_message)(
            conversation_id=conversation_id,
            role=message.role,
            content=message.content,
            feature_id=feature_id or "",
            tool_call_id=message.tool_call_id or "",
            tool_calls=[asdict(c) for c in message.tool_calls],
            citations=[asdict(c) for c in citations],
            steps=[to_record(s) for s in steps],
            trace=dict(trace_context or {}),
        )

    async def owned(self, conversation_id: UUID, staff_id: str) -> ConversationSummary | None:
        """The conversation if it belongs to `staff_id`, else None."""
        row = await sync_to_async(selectors.get_conversation)(
            conversation_id=conversation_id, staff_id=staff_id
        )
        return to_summary(row) if row else None

    async def list_for(self, staff_id: str, search: str = "") -> list[ConversationSummary]:
        rows = await sync_to_async(selectors.list_conversations)(staff_id=staff_id, search=search)
        return [to_summary(row) for row in rows]

    async def rename(
        self, conversation_id: UUID, staff_id: str, title: str
    ) -> ConversationSummary | None:
        row = await sync_to_async(services.rename_conversation)(
            conversation_id=conversation_id, staff_id=staff_id, title=title
        )
        return to_summary(row) if row else None

    async def delete(self, conversation_id: UUID, staff_id: str) -> bool:
        return await sync_to_async(services.delete_conversation)(
            conversation_id=conversation_id, staff_id=staff_id
        )

    async def history(
        self, conversation_id: UUID, staff_id: str | None = None
    ) -> list[HistoryMessage]:
        """The conversation as staff see it; with `staff_id`, each answer carries their rating."""
        rows = await sync_to_async(selectors.messages)(conversation_id=conversation_id)
        ratings = (
            await sync_to_async(selectors.feedback_of)(
                conversation_id=conversation_id, staff_id=staff_id
            )
            if staff_id
            else {}
        )
        return [
            HistoryMessage(
                r.id,
                r.role,
                r.content,
                r.feature_id or None,
                to_citations(r),
                r.created_at,
                tuple(from_record(s) for s in r.steps),
                to_rating(ratings[r.id]) if r.id in ratings else None,
            )
            for r in rows
            if r.role in VISIBLE_ROLES and (r.content or r.steps)
        ]

    async def rate(
        self,
        conversation_id: UUID,
        message_id: UUID,
        caller: Caller,
        rating: str,
        reason: str = "",
        comment: str = "",
    ) -> RatedAnswer | None:
        """Record the caller's rating of an answer in the conversation; None if there is no
        such answer. The caller must already be known to own the conversation."""
        message = await sync_to_async(selectors.answer)(
            conversation_id=conversation_id, message_id=message_id
        )
        if message is None:
            return None
        feedback = await sync_to_async(services.set_feedback)(
            message_id=message_id,
            staff_id=caller.id,
            role=caller.role,
            rating=rating,
            reason=reason,
            comment=comment,
        )
        return RatedAnswer(
            message.id, message.feature_id or None, dict(message.trace or {}), to_rating(feedback)
        )

    async def add_upload(
        self, conversation_id: UUID, filename: str, content_type: str, text: str
    ) -> UUID:
        upload = await sync_to_async(services.add_upload)(
            conversation_id=conversation_id, filename=filename, content_type=content_type, text=text
        )
        return upload.id

    async def upload_text(self, upload_id: UUID, conversation_id: UUID) -> str | None:
        upload = await sync_to_async(selectors.get_upload)(
            upload_id=upload_id, conversation_id=conversation_id
        )
        return upload.text if upload else None


def to_summary(row: ConversationRow) -> ConversationSummary:
    return ConversationSummary(row.id, row.title, row.updated_at)


def to_message(row: MessageRow) -> Message:
    """As the model reads it: the text with any playbook steps the turn showed."""
    return Message(
        role=row.role,
        content=as_text(row.content, (from_record(s) for s in row.steps)),
        tool_call_id=row.tool_call_id or None,
        tool_calls=tuple(ToolCall(**c) for c in row.tool_calls),
        created_at=row.created_at,
    )


def to_citations(row: MessageRow) -> tuple[Citation, ...]:
    return tuple(Citation(**c) for c in row.citations)


def to_rating(row: Any) -> Rating:
    return Rating(row.rating, row.reason, row.comment)
