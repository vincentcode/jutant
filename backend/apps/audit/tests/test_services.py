from uuid import uuid4

import pytest

from apps.audit import selectors, services
from apps.audit.masking import mask

pytestmark = pytest.mark.django_db


def test_events_are_stored_masked() -> None:
    conversation_id = uuid4()
    services.record_event(
        staff_id="S1",
        role="teller",
        event="question_asked",
        conversation_id=conversation_id,
        detail={"text": "Why did account 0011223344 fail? Email ama@example.com"},
    )
    [event] = selectors.events_for_conversation(conversation_id=conversation_id)
    assert event.detail["text"] == "Why did account ******3344 fail? Email ***@***"


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        ("acct 0011223344", "acct ******3344"),
        ("card 4111 1111 1111 1111", "card ************1111"),
        ("phone +233 24 123 4567", "phone ********4567"),
        ("id GHA-123456789-0", "id ******7890"),
        ("mail a.b@bank.co.uk", "mail ***@***"),
        (
            "date 2026-09-28, amount 1200.00, ref TX-0002",
            "date 2026-09-28, amount 1200.00, ref TX-0002",
        ),
    ],
)
def test_masking_patterns(text: str, masked: str) -> None:
    assert mask(text) == masked


def test_masking_reaches_nested_values_and_leaves_other_types() -> None:
    detail = {"arguments": {"account_number": "0011223344", "limit": 5}, "tools": ["a"]}
    assert mask(detail) == {
        "arguments": {"account_number": "******3344", "limit": 5},
        "tools": ["a"],
    }


def test_pack_patterns_replace_the_defaults() -> None:
    assert mask("policy POL-77", {"policy": r"POL-\d+"}) == "policy ****77"
