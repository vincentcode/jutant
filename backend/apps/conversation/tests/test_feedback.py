"""Feedback storage, and thumbs-down answers exported as draft eval questions."""

import pytest
import yaml
from django.core.management import call_command

from apps.conversation import services
from apps.conversation.models import Feedback
from apps.conversation.tests.factories import ConversationFactory, MessageFactory
from core.evals.scoring import EvalQuestion

pytestmark = pytest.mark.django_db


def answered(question: str, answer: str, feature: str = "transaction_lookup"):
    conversation = ConversationFactory()
    MessageFactory(conversation=conversation, role="user", content=question)
    return MessageFactory(
        conversation=conversation, role="assistant", content=answer, feature_id=feature
    )


def test_one_rating_per_person_per_answer_and_a_thumbs_up_drops_the_reason() -> None:
    message = answered("Why did TX-0002 fail?", "No idea.")
    services.set_feedback(
        message_id=message.id, staff_id="S1", role="teller", rating="down", reason="wrong_answer"
    )
    services.set_feedback(
        message_id=message.id, staff_id="S1", role="teller", rating="up", reason="wrong_answer"
    )
    services.set_feedback(message_id=message.id, staff_id="S2", role="teller", rating="down")
    mine = Feedback.objects.get(message=message, staff_id="S1")
    assert (mine.rating, mine.reason) == ("up", "")
    assert Feedback.objects.filter(message=message).count() == 2


def test_thumbs_down_answers_export_as_draft_eval_questions(tmp_path) -> None:
    wrong = answered('Why did "TX-0002" fail?\nUrgent', "It succeeded.")
    fine = answered("What is the rate on Standard Savings?", "8.5%.", feature="product_lookup")
    services.set_feedback(
        message_id=wrong.id,
        staff_id="S1",
        role="customer_service",
        rating="down",
        reason="wrong_answer",
        comment="It failed: account closed",
    )
    services.set_feedback(message_id=fine.id, staff_id="S1", role="teller", rating="up")

    out = tmp_path / "drafts.yaml"
    call_command("export_feedback", output=out)
    text = out.read_text(encoding="utf-8")

    [draft] = yaml.safe_load(text)
    question = EvalQuestion.from_dict(draft)  # loads as the evals read questions
    assert question.question == 'Why did "TX-0002" fail?\nUrgent'
    assert (question.feature, question.role) == ("transaction_lookup", "customer_service")
    assert "# Wrong answer: It failed: account closed" in text
    assert "# The answer was: It succeeded." in text
