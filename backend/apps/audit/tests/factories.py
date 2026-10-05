"""factory_boy factories that create `apps.audit` rows for tests."""

import factory

from apps.audit.models import AuditEvent


class AuditEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AuditEvent

    staff_id = "S0001"
    role = "teller"
    event = "question_asked"
    detail = factory.LazyFunction(dict)
