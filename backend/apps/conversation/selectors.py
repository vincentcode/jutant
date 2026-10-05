"""Every read query for conversations.

Staff read only their own conversations: every query that returns one takes the staff id.
"""

from uuid import UUID

from apps.conversation.models import Conversation, Message, Upload


def get_conversation(*, conversation_id: UUID, staff_id: str) -> Conversation | None:
    """The conversation if it belongs to `staff_id`, else None (callers answer 404)."""
    return Conversation.objects.filter(id=conversation_id, staff_id=staff_id).first()


def list_conversations(*, staff_id: str, limit: int = 50) -> list[Conversation]:
    return list(Conversation.objects.filter(staff_id=staff_id).order_by("-updated_at")[:limit])


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
