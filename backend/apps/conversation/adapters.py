"""Implements core.ports.ConversationStore on the conversation tables, plus the reads and
upload storage the API needs (the API reaches data through adapters, never the ORM)."""

from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID

from asgiref.sync import sync_to_async

from apps.conversation import selectors, services
from apps.conversation.models import Conversation as ConversationRow
from apps.conversation.models import Message as MessageRow
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
    ) -> None:
        await sync_to_async(services.add_message)(
            conversation_id=conversation_id,
            role=message.role,
            content=message.content,
            feature_id=feature_id or "",
            tool_call_id=message.tool_call_id or "",
            tool_calls=[asdict(c) for c in message.tool_calls],
            citations=[asdict(c) for c in citations],
        )

    async def owned(self, conversation_id: UUID, staff_id: str) -> ConversationSummary | None:
        """The conversation if it belongs to `staff_id`, else None."""
        row = await sync_to_async(selectors.get_conversation)(
            conversation_id=conversation_id, staff_id=staff_id
        )
        return to_summary(row) if row else None

    async def list_for(self, staff_id: str) -> list[ConversationSummary]:
        rows = await sync_to_async(selectors.list_conversations)(staff_id=staff_id)
        return [to_summary(row) for row in rows]

    async def history(self, conversation_id: UUID) -> list[HistoryMessage]:
        rows = await sync_to_async(selectors.messages)(conversation_id=conversation_id)
        return [
            HistoryMessage(
                r.id, r.role, r.content, r.feature_id or None, to_citations(r), r.created_at
            )
            for r in rows
            if r.role in VISIBLE_ROLES and r.content
        ]

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
    return Message(
        role=row.role,
        content=row.content,
        tool_call_id=row.tool_call_id or None,
        tool_calls=tuple(ToolCall(**c) for c in row.tool_calls),
        created_at=row.created_at,
    )


def to_citations(row: MessageRow) -> tuple[Citation, ...]:
    return tuple(Citation(**c) for c in row.citations)
