"""factory_boy factories that create `apps.identity` rows for tests."""

import factory
from django.contrib.auth import get_user_model

from apps.identity.models import Staff

PASSWORD = "correct horse"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ("username",)
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    first_name = "Ama"
    last_name = "Mensah"
    password = factory.PostGenerationMethodCall("set_password", PASSWORD)

    @factory.post_generation
    def save_password(obj, create, extracted, **kwargs):
        if create:
            obj.save()


class StaffFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Staff

    user = factory.SubFactory(UserFactory)
    staff_number = factory.Sequence(lambda n: f"S{n:04d}")
    role = "teller"
    attributes = factory.LazyFunction(lambda: {"branch": "ACC-01"})
