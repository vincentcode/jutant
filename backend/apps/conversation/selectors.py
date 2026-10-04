"""Every read query for conversations. Staff read only their own conversations."""

from uuid import UUID

from apps.conversation.models import Conversation, Message


def recent_messages(*, conversation_id: UUID, limit: int) -> list[Message]:
    raise NotImplementedError


def list_conversations(*, staff_id: UUID) -> list[Conversation]:
    raise NotImplementedError
