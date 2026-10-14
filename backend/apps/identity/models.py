import uuid

from django.conf import settings
from django.db import models


class Staff(models.Model):
    """A person. Their `role` (with `attributes`) is their role in whichever loaded pack defines
    it: a teller works in banking. Roles in other packs are `PackRole` rows: the same person is
    also an employee in HR."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    staff_number = models.CharField(max_length=64, unique=True)
    role = models.CharField(max_length=64, blank=True)  # a role of one of the loaded packs
    attributes = models.JSONField(default=dict, blank=True)  # caller attributes, e.g. branch
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "staff"

    def __str__(self) -> str:
        return f"{self.staff_number} ({self.role})"


class PackRole(models.Model):
    """A person's role in one pack, with that pack's attributes (a branch means nothing to HR).
    It takes precedence over `Staff.role` for that pack."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="pack_roles")
    pack = models.CharField(max_length=64)  # the pack's name: banking, hr
    role = models.CharField(max_length=64)
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["staff", "pack"], name="one_role_per_pack")]

    def __str__(self) -> str:
        return f"{self.pack}: {self.role}"


class LoginAttempt(models.Model):
    """One sign-in attempt, kept to limit password guessing. Old rows can be deleted freely."""

    username = models.CharField(max_length=150, db_index=True)  # as typed, lower-cased
    ip = models.GenericIPAddressField(null=True, blank=True)
    succeeded = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["ip", "created_at"])]
