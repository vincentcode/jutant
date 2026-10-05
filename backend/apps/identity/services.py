"""Every write for identity. Keyword-only arguments, atomic."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.identity.models import LoginAttempt, Staff

# Directory attributes copied onto the Django user when present.
USER_FIELDS = ("first_name", "last_name", "email")


@transaction.atomic
def sync_from_directory(*, username: str, directory_attrs: dict[str, Any]) -> Staff:
    """Create or update the user and Staff row from what the directory says about them.

    `staff_number`, `role` and `attributes` are taken from the directory when it provides them.
    A directory that does not (the development one) leaves them as operations staff set them.
    """
    user, _ = get_user_model().objects.get_or_create(username=username)
    changed = [f for f in USER_FIELDS if f in directory_attrs]
    for name in changed:
        setattr(user, name, directory_attrs[name] or "")
    if changed:
        user.save(update_fields=changed)

    from_directory = {
        k: directory_attrs[k]
        for k in ("staff_number", "role", "attributes")
        if k in directory_attrs
    }
    staff, created = Staff.objects.get_or_create(
        user=user, defaults={"staff_number": username, "role": "", **from_directory}
    )
    if from_directory and not created:
        for name, value in from_directory.items():
            setattr(staff, name, value)
        staff.save(update_fields=list(from_directory))
    return staff


@transaction.atomic
def set_role(*, staff_id: UUID, role: str) -> Staff:
    staff = Staff.objects.select_for_update().get(id=staff_id)
    staff.role = role
    staff.save(update_fields=["role"])
    return staff


@transaction.atomic
def set_active(*, staff_id: UUID, is_active: bool) -> Staff:
    staff = Staff.objects.select_for_update().get(id=staff_id)
    staff.is_active = is_active
    staff.save(update_fields=["is_active"])
    return staff


def record_login(*, username: str, ip: str | None, succeeded: bool) -> None:
    LoginAttempt.objects.create(username=username, ip=ip, succeeded=succeeded)


def delete_login_attempts(*, before: datetime) -> int:
    """Forget attempts older than `before`; they no longer count towards any limit."""
    deleted, _ = LoginAttempt.objects.filter(created_at__lt=before).delete()
    return deleted
