"""Reads of proposed actions: only the caller's own."""

from uuid import UUID

from apps.actions.models import ProposedAction


def for_conversation(conversation_id: UUID, staff_id: str) -> list[ProposedAction]:
    return list(ProposedAction.objects.filter(conversation_id=conversation_id, staff_id=staff_id))
