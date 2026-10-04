"""Every read query for audit."""

from uuid import UUID

from apps.audit.models import AuditEvent


def events_for_conversation(*, conversation_id: UUID) -> list[AuditEvent]:
    raise NotImplementedError
