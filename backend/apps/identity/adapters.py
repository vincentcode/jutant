"""Implements core.ports.IdentityProvider."""

from core.types import Caller


class DjangoIdentityProvider:
    def __init__(self, pack_roles: list[str]):
        self.pack_roles = pack_roles

    async def caller_for(self, user_id: str) -> Caller:
        """The role must be one of the loaded pack's roles."""
        raise NotImplementedError
