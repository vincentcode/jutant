"""Every write for identity. Keyword-only arguments, atomic."""

from typing import Any
from uuid import UUID

from django.db import transaction

from apps.identity.models import Staff


@transaction.atomic
def sync_from_directory(*, username: str, directory_attrs: dict[str, Any]) -> Staff:
    """Create or update the Staff row from the directory's attributes."""
    raise NotImplementedError


@transaction.atomic
def set_role(*, staff_id: UUID, role: str) -> Staff:
    raise NotImplementedError
