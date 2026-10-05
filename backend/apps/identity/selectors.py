"""Every read query for identity."""

from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser

from apps.identity.models import LoginAttempt, Staff


def get_staff(*, username: str) -> Staff | None:
    """The Staff row for a login name, with its user, or None."""
    return Staff.objects.select_related("user").filter(user__username=username).first()


def user_with_password(*, username: str, password: str) -> AbstractBaseUser | None:
    """The active Django user if the password matches. Used by the development directory."""
    user = get_user_model().objects.filter(username=username, is_active=True).first()
    if user is None or not user.check_password(password):
        return None
    return user


def failed_logins_for_user(*, username: str, since: datetime) -> list[datetime]:
    """When this username failed to sign in since `since`, counting only failures after its
    last successful sign-in. Oldest first."""
    attempts = LoginAttempt.objects.filter(username=username, created_at__gte=since)
    last_success = attempts.filter(succeeded=True).order_by("-created_at").first()
    if last_success is not None:
        attempts = attempts.filter(created_at__gt=last_success.created_at)
    return list(
        attempts.filter(succeeded=False).order_by("created_at").values_list("created_at", flat=True)
    )


def failed_logins_from_ip(*, ip: str, since: datetime) -> list[datetime]:
    """When sign-ins from this address failed since `since`, for any username. Oldest first."""
    return list(
        LoginAttempt.objects.filter(ip=ip, succeeded=False, created_at__gte=since)
        .order_by("created_at")
        .values_list("created_at", flat=True)
    )
