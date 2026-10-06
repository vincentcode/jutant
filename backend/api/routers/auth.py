"""Sign in, sign out, and who am I.

Signing in checks the credentials with the client's directory, keeps the staff record in step
with it, and sets the session cookie. Someone the directory knows but who has no role in this
pack gets 403 and no session. After repeated failures for a username or from an address,
sign-in is refused with 429 for a while (see LoginLimits).
"""

import math

from django.conf import settings
from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.deps import get_caller, get_client_ip, get_runtime, get_username
from api.schemas import LoginRequest, Me
from api.security import SESSION_COOKIE, issue_token
from config.container import Runtime
from core.errors import PolicyDenied
from core.types import Caller

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    runtime: Runtime = Depends(get_runtime),
    ip: str | None = Depends(get_client_ip),
) -> Me:
    # Checked before the password, so a locked account cannot be tried at all.
    if wait := await runtime.identity.login_wait(body.username, ip):
        minutes = math.ceil(wait / 60)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"too many failed sign-ins; try again in {minutes} minute{'s' * (minutes != 1)}",
            headers={"Retry-After": str(wait)},
        )
    succeeded = await runtime.identity.authenticate(body.username, body.password)
    await runtime.identity.record_login(body.username, ip, succeeded)
    if not succeeded:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong username or password")
    try:
        caller = await runtime.identity.caller_for(body.username)
    except PolicyDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no access to the assistant") from exc
    response.set_cookie(
        SESSION_COOKIE,
        issue_token(body.username, settings.JUTANT_SESSION_SECRET, settings.JUTANT_SESSION_TTL_MIN),
        max_age=settings.JUTANT_SESSION_TTL_MIN * 60,
        httponly=True,
        secure=settings.JUTANT_SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    return await _me(runtime, body.username, caller)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=settings.JUTANT_SESSION_COOKIE_SECURE,
        samesite="strict",
    )


@router.get("/me")
async def me(
    username: str = Depends(get_username),
    caller: Caller = Depends(get_caller),
    runtime: Runtime = Depends(get_runtime),
) -> Me:
    return await _me(runtime, username, caller)


async def _me(runtime: Runtime, username: str, caller: Caller) -> Me:
    return Me(
        id=caller.id,
        username=username,
        role=caller.role,
        display_name=await runtime.identity.display_name(username),
        attributes={k: str(v) for k, v in caller.attributes.items()},
    )
