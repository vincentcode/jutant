import pytest
from asgiref.sync import sync_to_async
from django.test.utils import override_settings

from api.security import SESSION_COOKIE, issue_token
from api.tests.conftest import api, make_staff
from apps.identity import services as identity_services

pytestmark = pytest.mark.django_db(transaction=True)


async def test_login_sets_a_strict_http_only_cookie_and_returns_the_caller() -> None:
    await make_staff("ama", staff_number="S0042")
    async with api() as client:
        response = await client.login("ama")
        assert response.status_code == 200
        assert response.json() == {
            "id": "S0042",
            "username": "ama",
            "role": "teller",
            "display_name": "Ama Mensah",
            "attributes": {"branch": "ACC-01"},
        }
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert (await client.http.get("/api/auth/me")).json()["role"] == "teller"


async def test_wrong_password_and_unknown_user_are_401() -> None:
    await make_staff("ama")
    async with api() as client:
        assert (await client.login("ama", "wrong")).status_code == 401
        assert (await client.login("nobody")).status_code == 401


async def test_user_without_a_role_in_the_pack_gets_403_and_no_session() -> None:
    await make_staff("kofi", role="")
    async with api() as client:
        response = await client.login("kofi")
        assert response.status_code == 403
        assert "set-cookie" not in response.headers


async def test_no_cookie_bad_cookie_and_expired_cookie_are_401() -> None:
    await make_staff("ama")
    async with api() as client:
        assert (await client.http.get("/api/auth/me")).status_code == 401
        client.http.cookies.set(SESSION_COOKIE, "forged.token")
        assert (await client.http.get("/api/auth/me")).status_code == 401
        from django.conf import settings

        expired = issue_token("ama", settings.JUTANT_SESSION_SECRET, ttl_min=1, now=0)
        client.http.cookies.set(SESSION_COOKIE, expired)
        assert (await client.http.get("/api/auth/me")).status_code == 401


async def test_logout_ends_the_session() -> None:
    await make_staff("ama")
    async with api() as client:
        await client.login("ama")
        assert (await client.http.post("/api/auth/logout")).status_code == 204
        assert (await client.http.get("/api/auth/me")).status_code == 401


async def test_a_role_change_in_the_admin_applies_at_once() -> None:
    staff = await make_staff("ama")
    async with api() as client:
        await client.login("ama")
        await sync_to_async(identity_services.set_role)(staff_id=staff.id, role="branch_manager")
        assert (await client.http.get("/api/auth/me")).json()["role"] == "branch_manager"
        await sync_to_async(identity_services.set_active)(staff_id=staff.id, is_active=False)
        assert (await client.http.get("/api/auth/me")).status_code == 403


# --- limits on password guessing ---------------------------------------------------------


async def test_a_username_is_locked_after_five_failures_even_for_the_right_password() -> None:
    await make_staff("ama")
    async with api() as client:
        for _ in range(5):
            assert (await client.login("ama", "wrong")).status_code == 401
        locked = await client.login("ama")  # the right password
        assert locked.status_code == 429
        assert "try again in 15 minutes" in locked.json()["detail"]
        assert 0 < int(locked.headers["retry-after"]) <= 15 * 60
        # Another account from the same address is not affected by this lock.
        await make_staff("kofi")
        assert (await client.login("kofi")).status_code == 200


async def test_a_successful_sign_in_resets_the_count() -> None:
    await make_staff("ama")
    async with api() as client:
        for _ in range(4):
            await client.login("ama", "wrong")
        assert (await client.login("ama")).status_code == 200
        for _ in range(4):
            await client.login("ama", "wrong")
        assert (await client.login("ama")).status_code == 200


async def test_unknown_usernames_are_locked_the_same_way() -> None:
    async with api() as client:
        for _ in range(5):
            assert (await client.login("nobody", "guess")).status_code == 401
        assert (await client.login("NOBODY ", "guess")).status_code == 429  # same account


async def test_one_address_trying_many_usernames_is_locked() -> None:
    with override_settings(JUTANT_LOGIN_MAX_FAILURES_PER_IP=3):
        await make_staff("ama")
        async with api() as client:
            for name in ("user1", "user2", "user3"):
                assert (await client.login(name, "Password1")).status_code == 401
            assert (await client.login("ama")).status_code == 429


def test_forwarded_address_is_believed_only_from_a_trusted_proxy() -> None:
    from starlette.requests import Request

    from api.deps import get_client_ip

    def request(peer: str, forwarded: str) -> Request:
        headers = [(b"x-forwarded-for", forwarded.encode())]
        return Request({"type": "http", "client": (peer, 1234), "headers": headers})

    with override_settings(JUTANT_TRUSTED_PROXIES=["172.16.0.0/12"]):
        assert get_client_ip(request("172.18.0.5", "10.1.2.3")) == "10.1.2.3"
        # A forged entry before the real one is skipped: the proxy set the last one.
        assert get_client_ip(request("172.18.0.5", "6.6.6.6, 10.1.2.3")) == "10.1.2.3"
        # Someone reaching the API directly cannot choose their address.
        assert get_client_ip(request("10.9.9.9", "1.2.3.4")) == "10.9.9.9"
    with override_settings(JUTANT_TRUSTED_PROXIES=[]):
        assert get_client_ip(request("172.18.0.5", "10.1.2.3")) == "172.18.0.5"
