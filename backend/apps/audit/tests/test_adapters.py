from uuid import uuid4

import pytest
from asgiref.sync import sync_to_async

from apps.audit import selectors
from apps.audit.adapters import DjangoAuditSink
from core.types import Caller

pytestmark = pytest.mark.django_db(transaction=True)


async def test_sink_records_against_the_caller_and_conversation() -> None:
    conversation_id = uuid4()
    caller = Caller("S0042", "teller", "staff", {})
    await DjangoAuditSink().record(
        caller, "tool_called", {"conversation_id": str(conversation_id), "tool": "documents.search"}
    )
    [event] = await sync_to_async(selectors.events_for_conversation)(
        conversation_id=conversation_id
    )
    assert (event.staff_id, event.role, event.event) == ("S0042", "teller", "tool_called")
