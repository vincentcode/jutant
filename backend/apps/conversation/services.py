"""Every write for conversations. Keyword-only arguments, atomic."""

from typing import Any
from uuid import UUID

from django.db import transaction

from apps.conversation.models import Conversation, Message


@transaction.atomic
def start_conversation(*, staff_id: UUID) -> Conversation:
    raise NotImplementedError


@transaction.atomic
def add_message(
    *,
    conversation_id: UUID,
    role: str,
    content: str,
    feature_id: str = "",
    tool_call_id: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> Message:
    raise NotImplementedError
