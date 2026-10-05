"""Implements core.ports.IdentityProvider: turns a logged-in user into a core Caller."""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.identity import directory, selectors, services
from core.errors import PolicyDenied
from core.types import Caller

STAFF_AUDIENCE = "staff"


@dataclass(frozen=True)
class LoginLimits:
    """Password guessing limits. A username is locked after `per_user` failures in `window`
    (failures before its last successful sign-in do not count); an address after `per_ip`
    failures in `window` across all usernames, which stops one address trying a common password
    on many accounts. Either lock lifts as the failures age out of the window."""

    per_user: int = 5
    per_ip: int = 20
    window: timedelta = timedelta(minutes=15)


class DjangoIdentityProvider:
    def __init__(self, pack_roles: Iterable[str], limits: LoginLimits | None = None):
        self.pack_roles = frozenset(pack_roles)
        self.limits = limits or LoginLimits()

    async def login_wait(self, username: str, ip: str | None) -> int:
        """Seconds until this username, from this address, may try to sign in again; 0 if now.

        Any username is counted, whether or not it exists, so a lock reveals nothing about
        which accounts exist."""
        now = timezone.now()
        since = now - self.limits.window
        waits = [0.0]
        by_user = await sync_to_async(selectors.failed_logins_for_user)(
            username=_key(username), since=since
        )
        waits.append(self._wait(by_user, self.limits.per_user, now))
        if ip:
            by_ip = await sync_to_async(selectors.failed_logins_from_ip)(ip=ip, since=since)
            waits.append(self._wait(by_ip, self.limits.per_ip, now))
        return math.ceil(max(waits))

    async def record_login(self, username: str, ip: str | None, succeeded: bool) -> None:
        await sync_to_async(services.record_login)(
            username=_key(username), ip=ip, succeeded=succeeded
        )

    def _wait(self, failures: list[datetime], limit: int, now: datetime) -> float:
        """Until enough of the failures leave the window to bring them under the limit."""
        if len(failures) < limit:
            return 0.0
        return (failures[-limit] + self.limits.window - now).total_seconds()

    async def caller_for(self, user_id: str) -> Caller:
        """`user_id` is the login name. Raises PolicyDenied for an unknown, inactive or
        unassigned user, or a role the loaded pack does not define."""
        staff = await sync_to_async(selectors.get_staff)(username=user_id)
        if staff is None or not staff.is_active or not staff.user.is_active:
            raise PolicyDenied("no active staff record")
        if staff.role not in self.pack_roles:
            raise PolicyDenied(f"role {staff.role!r} is not a role of this pack")
        return Caller(
            id=staff.staff_number,
            role=staff.role,
            audience=STAFF_AUDIENCE,
            attributes=dict(staff.attributes or {}),
        )

    async def authenticate(self, username: str, password: str) -> bool:
        """Check the credentials with the directory and bring the staff record up to date."""
        attrs = await sync_to_async(directory.verify)(username, password)
        if attrs is None:
            return False
        await sync_to_async(services.sync_from_directory)(username=username, directory_attrs=attrs)
        return True

    async def display_name(self, user_id: str) -> str:
        staff = await sync_to_async(selectors.get_staff)(username=user_id)
        if staff is None:
            return user_id
        return staff.user.get_full_name() or staff.user.get_username()


def _key(username: str) -> str:
    """The username as attempts are counted: "Ama" and "ama " are the same account to a guesser."""
    return username.strip().lower()
