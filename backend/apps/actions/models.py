"""Requests the assistant proposed, waiting for the person to send them (`core.actions`)."""

import uuid

from django.db import models


class ProposedAction(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "proposed"
        SENDING = "sending"
        SENT = "sent"
        FAILED = "failed"
        CANCELLED = "cancelled"
        EXPIRED = "expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation_id = models.UUIDField(db_index=True)
    staff_id = models.CharField(max_length=64)  # who proposed it: only they may send it
    action_id = models.CharField(max_length=64)
    title = models.CharField(max_length=200)
    icon = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    fields = models.JSONField(default=list)  # [{"label", "value"}], as the card shows them
    notes = models.JSONField(default=list)
    warnings = models.JSONField(default=list)
    submit = models.JSONField(default=dict)  # the perform tool's arguments, exactly
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED)
    reference = models.CharField(max_length=300, blank=True)
    outcome = models.CharField(max_length=300, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)  # sent, failed or cancelled

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"
