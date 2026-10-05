"""Every read query for audit."""

from uuid import UUID

from apps.audit.models import AuditEvent


def events_for_conversation(*, conversation_id: UUID) -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(conversation_id=conversation_id).order_by("at"))


def events_for_staff(*, staff_id: str, limit: int = 100) -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(staff_id=staff_id).order_by("-at")[:limit])
