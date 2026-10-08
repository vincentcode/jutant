from io import StringIO
from uuid import uuid4

import pytest
from django.core.management import call_command

from apps.audit import services

pytestmark = pytest.mark.django_db


def test_the_report_counts_pickers_from_the_audit_log() -> None:
    conversation = uuid4()
    for event, detail in [
        ("question_asked", {"text": "why?"}),
        ("clarify_shown", {"reason": "unread", "choices": [{"kind": "subject"}]}),
        ("question_asked", {"text": "why?", "picked": 0}),
    ]:
        services.record_event(
            staff_id="S1", role="teller", event=event, detail=detail, conversation_id=conversation
        )
    out = StringIO()
    call_command("report_turns", stdout=out)
    assert "picker shown        1 (100% of messages)" in out.getvalue()
    assert "first choice      1 (100% of picks)" in out.getvalue()
