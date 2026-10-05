"""factory_boy factories that create `apps.conversation` rows for tests."""

import factory

from apps.conversation.models import Conversation, Message


class ConversationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Conversation

    staff_id = "S0001"


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    role = Message.Role.USER
    content = factory.Sequence(lambda n: f"message {n}")
