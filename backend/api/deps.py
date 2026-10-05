"""FastAPI dependencies: the runtime, the logged-in user, the caller and their address."""

import ipaddress

from django.conf import settings
from fastapi import Depends, HTTPException, Request, status

from api.security import SESSION_COOKIE, InvalidSession, verify_token
from config.container import Runtime
from core.errors import PolicyDenied
from core.orchestrator.orchestrator import Orchestrator
from core.types import Caller


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_orchestrator(runtime: Runtime = Depends(get_runtime)) -> Orchestrator:
    return runtime.orchestrator


def get_username(request: Request) -> str:
    """The login name from the session cookie; 401 if there is no valid session."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    try:
        return verify_token(token, settings.JUTANT_SESSION_SECRET)
    except InvalidSession as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired") from exc


async def get_caller(
    username: str = Depends(get_username), runtime: Runtime = Depends(get_runtime)
) -> Caller:
    """The caller for this request, looked up fresh: 403 if they have no role in this pack."""
    try:
        return await runtime.identity.caller_for(username)
    except PolicyDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no access to the assistant") from exc


def get_client_ip(request: Request) -> str | None:
    """The browser's address. Behind a trusted proxy (JUTANT_TRUSTED_PROXIES), the nearest
    address in X-Forwarded-For that is not itself a trusted proxy; otherwise the connecting
    address, since anyone else could write any X-Forwarded-For they like."""
    peer = request.client.host if request.client else None
    if peer is None or not _trusted(peer):
        return peer
    forwarded = [a.strip() for a in request.headers.get("x-forwarded-for", "").split(",")]
    for address in reversed([a for a in forwarded if a]):
        if not _trusted(address):
            return address
    return peer


def _trusted(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in ipaddress.ip_network(n, strict=False) for n in settings.JUTANT_TRUSTED_PROXIES)
