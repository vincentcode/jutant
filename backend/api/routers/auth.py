from fastapi import APIRouter, Depends, Response

from api.deps import get_caller
from api.schemas import LoginRequest, Me
from core.types import Caller

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> Me:
    raise NotImplementedError


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    raise NotImplementedError


@router.get("/me")
async def me(caller: Caller = Depends(get_caller)) -> Me:
    raise NotImplementedError
