"""The sign-in limits on the identity adapter: when a lock starts and when it lifts."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.identity.adapters import DjangoIdentityProvider, LoginLimits
from apps.identity.models import LoginAttempt

pytestmark = pytest.mark.django_db(transaction=True)


def provider(**limits) -> DjangoIdentityProvider:
    return DjangoIdentityProvider(["teller"], LoginLimits(**limits))


async def fail(identity: DjangoIdentityProvider, username: str, times: int, ip="10.0.0.1"):
    for _ in range(times):
        await identity.record_login(username, ip, succeeded=False)


async def test_the_lock_starts_at_the_limit_and_lasts_the_window() -> None:
    identity = provider(per_user=3, window=timedelta(minutes=10))
    await fail(identity, "ama", 2)
    assert await identity.login_wait("ama", "10.0.0.1") == 0
    await fail(identity, "ama", 1)
    assert 590 <= await identity.login_wait("ama", "10.0.0.1") <= 600


async def test_the_lock_lifts_as_failures_age_out_of_the_window() -> None:
    identity = provider(per_user=3, window=timedelta(minutes=10))
    await fail(identity, "ama", 3)
    await LoginAttempt.objects.filter(username="ama").aupdate(
        created_at=timezone.now() - timedelta(minutes=11)
    )
    assert await identity.login_wait("ama", "10.0.0.1") == 0


async def test_usernames_are_counted_ignoring_case_and_spaces() -> None:
    identity = provider(per_user=2)
    await fail(identity, "Ama", 1)
    await fail(identity, " ama ", 1)
    assert await identity.login_wait("AMA", None) > 0


async def test_an_address_is_locked_across_usernames() -> None:
    identity = provider(per_user=5, per_ip=3)
    for name in ("a", "b", "c"):
        await fail(identity, name, 1, ip="10.0.0.9")
    assert await identity.login_wait("d", "10.0.0.9") > 0
    assert await identity.login_wait("d", "10.0.0.10") == 0
