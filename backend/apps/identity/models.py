import uuid

from django.conf import settings
from django.db import models


class Staff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    staff_number = models.CharField(max_length=64, unique=True)
    role = models.CharField(max_length=64)  # one of the loaded pack's roles
    attributes = models.JSONField(default=dict, blank=True)  # caller attributes, e.g. branch
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "staff"

    def __str__(self) -> str:
        return f"{self.staff_number} ({self.role})"


class LoginAttempt(models.Model):
    """One sign-in attempt, kept to limit password guessing. Old rows can be deleted freely."""

    username = models.CharField(max_length=150, db_index=True)  # as typed, lower-cased
    ip = models.GenericIPAddressField(null=True, blank=True)
    succeeded = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["ip", "created_at"])]
