import pytest
from django.core.management import call_command

from apps.playbooks import selectors, services
from apps.playbooks.adapters import to_playbook
from apps.playbooks.tests.factories import BLOCKED_CARD

pytestmark = pytest.mark.django_db


def test_upsert_round_trips_a_playbook() -> None:
    row, written = services.upsert_playbook(definition=BLOCKED_CARD)
    assert written
    assert to_playbook(selectors.get_playbook(slug="blocked_card")) == BLOCKED_CARD
    assert row.version == 1


def test_existing_playbooks_are_kept_unless_replaced() -> None:
    services.upsert_playbook(definition=BLOCKED_CARD)
    row = selectors.get_playbook(slug="blocked_card")
    row.title = "Edited in the admin"
    row.save()

    _, written = services.upsert_playbook(definition=BLOCKED_CARD)
    assert not written
    assert selectors.get_playbook(slug="blocked_card").title == "Edited in the admin"

    replaced, written = services.upsert_playbook(definition=BLOCKED_CARD, replace=True)
    assert written
    assert replaced.title == "Blocked card"
    assert replaced.version == 2
    assert replaced.steps.count() == 3


def test_inactive_playbooks_are_not_offered() -> None:
    row, _ = services.upsert_playbook(definition=BLOCKED_CARD)
    row.is_active = False
    row.save()
    assert selectors.get_playbook(slug="blocked_card") is None
    assert selectors.list_playbooks() == []


def test_one_active_run_per_conversation() -> None:
    from uuid import uuid4

    conversation_id = uuid4()
    first = services.save_run(
        conversation_id=conversation_id,
        playbook_id="blocked_card",
        current_order=1,
        answers={},
        status="active",
    )
    same = services.save_run(
        conversation_id=conversation_id,
        playbook_id="blocked_card",
        current_order=2,
        answers={1: "confirm"},
        status="completed",
    )
    assert same.id == first.id
    assert selectors.active_run(conversation_id=conversation_id) is None
    again = services.save_run(
        conversation_id=conversation_id,
        playbook_id="blocked_card",
        current_order=1,
        answers={},
        status="active",
    )
    assert again.id != first.id


def test_load_pack_playbooks_command() -> None:
    call_command("load_pack_playbooks")
    assert {p.slug for p in selectors.list_playbooks()} == {
        "blocked_card",
        "dormant_account",
        "failed_transfer",
    }
