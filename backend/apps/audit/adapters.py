"""Implements core.ports.AuditSink."""

from typing import Any

from core.types import Caller


class DjangoAuditSink:
    async def record(self, caller: Caller, event: str, detail: dict[str, Any]) -> None:
        raise NotImplementedError
