"""Every write for conversations. Keyword-only arguments, atomic."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.conversation.models import Conversation, Message, Upload

TITLE_LENGTH = 60


@transaction.atomic
def start_conversation(*, staff_id: str) -> Conversation:
    return Conversation.objects.create(staff_id=staff_id)


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
    """Append a message. The first user message also becomes the conversation's title."""
    conversation = Conversation.objects.select_for_update().get(id=conversation_id)
    message = Message.objects.create(
        conversation=conversation,
        role=role,
        content=content,
        feature_id=feature_id,
        tool_call_id=tool_call_id,
        tool_calls=tool_calls or [],
        citations=citations or [],
    )
    if not conversation.title and role == Message.Role.USER:
        conversation.title = _title(content)
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=["title", "updated_at"])
    return message


def _title(content: str) -> str:
    text = " ".join(content.split())
    return text if len(text) <= TITLE_LENGTH else text[: TITLE_LENGTH - 1].rstrip() + "…"


@transaction.atomic
def add_upload(*, conversation_id: UUID, filename: str, content_type: str, text: str) -> Upload:
    return Upload.objects.create(
        conversation_id=conversation_id, filename=filename, content_type=content_type, text=text
    )


def delete_uploads(*, before: datetime) -> int:
    """Delete uploaded files' text older than `before`. Answers already given from them stay
    in their conversations."""
    deleted, _ = Upload.objects.filter(created_at__lt=before).delete()
    return deleted
