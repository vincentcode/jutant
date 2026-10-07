"""Every write for conversations. Keyword-only arguments, atomic."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.conversation.models import Conversation, Feedback, Message, Upload

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
    steps: list[dict[str, Any]] | None = None,
    trace: dict[str, str] | None = None,
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
        steps=steps or [],
        trace=trace or {},
    )
    if not conversation.title and role == Message.Role.USER:
        conversation.title = _title(content)
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=["title", "updated_at"])
    return message


def save_context(*, conversation_id: UUID, context: dict[str, Any]) -> None:
    """Keep the conversation's context (its stack of subjects) for the next turn."""
    Conversation.objects.filter(id=conversation_id).update(context=context)


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


@transaction.atomic
def set_feedback(
    *,
    message_id: UUID,
    staff_id: str,
    role: str,
    rating: str,
    reason: str = "",
    comment: str = "",
) -> Feedback:
    """Record or change a staff member's rating of an answer. A thumbs-up clears any reason."""
    feedback, _ = Feedback.objects.update_or_create(
        message_id=message_id,
        staff_id=staff_id,
        defaults={
            "role": role,
            "rating": rating,
            "reason": reason if rating == Feedback.Rating.DOWN else "",
            "comment": comment.strip(),
        },
    )
    return feedback


def rename_conversation(*, conversation_id: UUID, staff_id: str, title: str) -> Conversation | None:
    conversation = Conversation.objects.filter(id=conversation_id, staff_id=staff_id).first()
    if conversation is None:
        return None
    conversation.title = title[: TITLE_LENGTH * 2]
    conversation.save(update_fields=["title"])
    return conversation


@transaction.atomic
def delete_conversation(*, conversation_id: UUID, staff_id: str) -> bool:
    """Delete it with its messages, uploads and ratings (they cascade)."""
    deleted, _ = Conversation.objects.filter(id=conversation_id, staff_id=staff_id).delete()
    return deleted > 0
