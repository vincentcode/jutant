"""Implements core.ports.AuditSink on the audit table."""

from collections.abc import Mapping
from typing import Any

from asgiref.sync import sync_to_async

from apps.audit import services
from core.types import Caller


class DjangoAuditSink:
    def __init__(self, patterns: Mapping[str, str] | None = None):
        self.patterns = patterns  # masking patterns; None uses the defaults

    async def record(self, caller: Caller, event: str, detail: dict[str, Any]) -> None:
        await sync_to_async(services.record_event)(
            staff_id=caller.id,
            role=caller.role,
            event=event,
            detail=detail,
            conversation_id=detail.get("conversation_id"),
            patterns=self.patterns,
        )
