"""Implements core.ports.ConversationStore."""

from uuid import UUID

from core.types import Caller, Message


class DjangoConversationStore:
    async def create(self, caller: Caller) -> UUID:
        raise NotImplementedError

    async def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]:
        raise NotImplementedError

    async def append(
        self, conversation_id: UUID, message: Message, feature_id: str | None = None
    ) -> None:
        raise NotImplementedError
