"""Every read query for identity."""

from apps.identity.models import Staff


def get_staff(*, user_id: str) -> Staff:
    raise NotImplementedError
