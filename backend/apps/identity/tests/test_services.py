import pytest

from apps.identity import directory, services
from apps.identity.backends import DirectoryBackend
from apps.identity.tests.factories import PASSWORD, StaffFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_first_login_creates_staff_without_a_role() -> None:
    staff = services.sync_from_directory(username="kofi", directory_attrs={"first_name": "Kofi"})
    assert staff.user.first_name == "Kofi"
    assert staff.staff_number == "kofi"
    assert staff.role == ""


def test_directory_attributes_update_an_existing_staff_row() -> None:
    staff = StaffFactory(role="teller")
    updated = services.sync_from_directory(
        username=staff.user.username,
        directory_attrs={"role": "branch_manager", "attributes": {"branch": "KSI-02"}},
    )
    assert updated.id == staff.id
    assert updated.role == "branch_manager"
    assert updated.attributes == {"branch": "KSI-02"}


def test_a_directory_without_roles_keeps_the_role_set_by_operations() -> None:
    staff = StaffFactory(role="credit_officer")
    services.sync_from_directory(username=staff.user.username, directory_attrs={"email": "a@b.c"})
    staff.refresh_from_db()
    assert staff.role == "credit_officer"


def test_set_role() -> None:
    staff = StaffFactory(role="teller")
    assert services.set_role(staff_id=staff.id, role="branch_manager").role == "branch_manager"


def test_development_directory_checks_the_password() -> None:
    user = UserFactory()
    assert directory.verify(user.username, PASSWORD) == {
        "first_name": "Ama",
        "last_name": "Mensah",
        "email": "",
    }
    assert directory.verify(user.username, "wrong") is None
    assert directory.verify("nobody", PASSWORD) is None


def test_admin_backend_logs_in_through_the_directory() -> None:
    user = UserFactory()
    backend = DirectoryBackend()
    assert backend.authenticate(None, username=user.username, password=PASSWORD) == user
    assert backend.authenticate(None, username=user.username, password="wrong") is None
