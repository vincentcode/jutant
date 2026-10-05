import pytest

from apps.conversation import selectors, services
from apps.conversation.tests.factories import ConversationFactory, MessageFactory

pytestmark = pytest.mark.django_db


def test_first_user_message_becomes_the_title() -> None:
    conversation = services.start_conversation(staff_id="S1")
    services.add_message(
        conversation_id=conversation.id, role="user", content="What is the KYC rule?"
    )
    services.add_message(conversation_id=conversation.id, role="user", content="Second question")
    conversation.refresh_from_db()
    assert conversation.title == "What is the KYC rule?"


def test_long_titles_are_shortened() -> None:
    conversation = services.start_conversation(staff_id="S1")
    services.add_message(conversation_id=conversation.id, role="user", content="word " * 40)
    conversation.refresh_from_db()
    assert len(conversation.title) <= 60
    assert conversation.title.endswith("…")


def test_recent_messages_are_the_latest_oldest_first() -> None:
    conversation = ConversationFactory()
    for n in range(5):
        MessageFactory(conversation=conversation, content=f"m{n}")
    recent = selectors.recent_messages(conversation_id=conversation.id, limit=3)
    assert [m.content for m in recent] == ["m2", "m3", "m4"]
    assert selectors.recent_messages(conversation_id=conversation.id, limit=0) == []


def test_staff_see_only_their_own_conversations() -> None:
    mine = ConversationFactory(staff_id="S1")
    ConversationFactory(staff_id="S2")
    assert selectors.list_conversations(staff_id="S1") == [mine]
    assert selectors.get_conversation(conversation_id=mine.id, staff_id="S1") == mine
    assert selectors.get_conversation(conversation_id=mine.id, staff_id="S2") is None


def test_list_is_most_recently_used_first() -> None:
    older = services.start_conversation(staff_id="S1")
    newer = services.start_conversation(staff_id="S1")
    services.add_message(conversation_id=older.id, role="user", content="bump")
    assert selectors.list_conversations(staff_id="S1") == [older, newer]
