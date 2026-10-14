import pytest
from asgiref.sync import sync_to_async

from apps.identity.adapters import DjangoIdentityProvider
from apps.identity.models import PackRole
from apps.identity.tests.factories import StaffFactory
from core.errors import PolicyDenied
from core.types import Caller
from core.types import PackRole as CorePackRole

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


BOTH = {"banking": ["teller", "branch_manager"], "hr": ["employee"]}


async def test_a_person_has_a_role_in_each_pack_they_belong_to() -> None:
    staff = await sync_to_async(StaffFactory)(role="teller", attributes={"branch": "ACC-01"})
    await sync_to_async(PackRole.objects.create)(staff=staff, pack="hr", role="employee")
    caller = await DjangoIdentityProvider(BOTH).caller_for(staff.user.username)
    assert caller.packs == {
        "banking": CorePackRole("teller", {"branch": "ACC-01"}),
        "hr": CorePackRole("employee", {}),
    }
    assert caller.in_pack("hr").role == "employee"


async def test_a_role_no_loaded_pack_has_gives_no_access() -> None:
    staff = await sync_to_async(StaffFactory)(role="employee", attributes={})
    await sync_to_async(PackRole.objects.create)(staff=staff, pack="payroll", role="clerk")
    caller = await DjangoIdentityProvider(BOTH).caller_for(staff.user.username)
    assert list(caller.packs) == ["hr"]  # employee is HR's; payroll is not loaded
    nobody = await sync_to_async(StaffFactory)(role="auditor", attributes={})
    with pytest.raises(PolicyDenied):
        await DjangoIdentityProvider(BOTH).caller_for(nobody.user.username)
