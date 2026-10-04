import uuid

from django.db import models


class AuditEvent(models.Model):
    """Append-only: no update or delete in services or admin."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    staff_id = models.CharField(max_length=64, db_index=True)
    role = models.CharField(max_length=64)
    conversation_id = models.UUIDField(null=True, blank=True, db_index=True)
    event = models.CharField(max_length=64, db_index=True)
    detail = models.JSONField(default=dict)
