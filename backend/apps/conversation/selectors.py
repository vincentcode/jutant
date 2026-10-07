"""Every read query for conversations.

Staff read only their own conversations: every query that returns one takes the staff id.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import Q

from apps.conversation.models import Conversation, Feedback, Message, Upload


def get_conversation(*, conversation_id: UUID, staff_id: str) -> Conversation | None:
    """The conversation if it belongs to `staff_id`, else None (callers answer 404)."""
    return Conversation.objects.filter(id=conversation_id, staff_id=staff_id).first()


def context(*, conversation_id: UUID) -> dict[str, Any]:
    """The conversation's context (its stack of subjects), or empty."""
    row = Conversation.objects.filter(id=conversation_id).values_list("context", flat=True).first()
    return dict(row or {})


def list_conversations(*, staff_id: str, search: str = "", limit: int = 50) -> list[Conversation]:
    """The staff member's conversations, latest first; with `search`, those whose title or any
    message contains it."""
    rows = Conversation.objects.filter(staff_id=staff_id)
    if search:
        rows = rows.filter(
            Q(title__icontains=search) | Q(messages__content__icontains=search)
        ).distinct()
    return list(rows.order_by("-updated_at")[:limit])


def recent_messages(*, conversation_id: UUID, limit: int) -> list[Message]:
    """The last `limit` messages, oldest first."""
    if limit <= 0:
        return []
    latest = Message.objects.filter(conversation_id=conversation_id).order_by("-created_at")
    return list(reversed(latest[:limit]))


def messages(*, conversation_id: UUID) -> list[Message]:
    """The whole conversation, oldest first."""
    return list(Message.objects.filter(conversation_id=conversation_id).order_by("created_at"))


def get_upload(*, upload_id: UUID, conversation_id: UUID) -> Upload | None:
    """The upload if it belongs to the conversation, else None."""
    return Upload.objects.filter(id=upload_id, conversation_id=conversation_id).first()


def answer(*, conversation_id: UUID, message_id: UUID) -> Message | None:
    """An assistant message of the conversation, or None."""
    return Message.objects.filter(
        id=message_id, conversation_id=conversation_id, role=Message.Role.ASSISTANT
    ).first()


def feedback_of(*, conversation_id: UUID, staff_id: str) -> dict[UUID, Feedback]:
    """The staff member's ratings in the conversation, by message."""
    rows = Feedback.objects.filter(message__conversation_id=conversation_id, staff_id=staff_id)
    return {f.message_id: f for f in rows}


def question_before(message: Message) -> Message | None:
    """The staff member's question an answer replied to."""
    return (
        Message.objects.filter(
            conversation_id=message.conversation_id,
            role=Message.Role.USER,
            created_at__lte=message.created_at,
        )
        .order_by("-created_at")
        .first()
    )


def thumbs_down(*, since: datetime | None = None) -> list[Feedback]:
    """Thumbs-down ratings, newest first, with their answers."""
    rows = Feedback.objects.filter(rating=Feedback.Rating.DOWN).select_related("message")
    if since is not None:
        rows = rows.filter(updated_at__gte=since)
    return list(rows.order_by("-updated_at"))
