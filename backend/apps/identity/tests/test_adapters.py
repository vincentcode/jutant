import pytest

from apps.identity.adapters import DjangoIdentityProvider
from apps.identity.tests.factories import StaffFactory
from core.errors import PolicyDenied
from core.types import Caller

pytestmark = pytest.mark.django_db(transaction=True)
ROLES = ["teller", "branch_manager"]


async def make_staff(**kwargs):
    from asgiref.sync import sync_to_async

    return await sync_to_async(StaffFactory)(**kwargs)


async def test_caller_for_a_staff_member() -> None:
    staff = await make_staff(staff_number="S0042", role="teller")
    caller = await DjangoIdentityProvider(ROLES).caller_for(staff.user.username)
    assert caller == Caller("S0042", "teller", "staff", {"branch": "ACC-01"})


async def test_unknown_inactive_and_foreign_roles_are_refused() -> None:
    provider = DjangoIdentityProvider(ROLES)
    inactive = await make_staff(is_active=False)
    unassigned = await make_staff(role="")
    foreign = await make_staff(role="claims_handler")
    for username in (
        "nobody",
        inactive.user.username,
        unassigned.user.username,
        foreign.user.username,
    ):
        with pytest.raises(PolicyDenied):
            await provider.caller_for(username)


async def test_display_name() -> None:
    staff = await make_staff()
    assert await DjangoIdentityProvider(ROLES).display_name(staff.user.username) == "Ama Mensah"
