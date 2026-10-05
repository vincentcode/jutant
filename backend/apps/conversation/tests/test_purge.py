"""purge_expired deletes old uploads and sign-in attempts, and nothing newer."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.conversation import services
from apps.conversation.models import Upload
from apps.conversation.tests.factories import ConversationFactory
from apps.identity import services as identity_services
from apps.identity.models import LoginAttempt

pytestmark = pytest.mark.django_db


def test_old_uploads_and_attempts_are_deleted_and_recent_ones_kept(settings) -> None:
    settings.JUTANT_UPLOAD_RETENTION_DAYS = 30
    settings.JUTANT_LOGIN_ATTEMPT_RETENTION_DAYS = 7
    conversation = ConversationFactory()
    for name in ("old.pdf", "new.pdf"):
        services.add_upload(
            conversation_id=conversation.id, filename=name, content_type="", text="ID CARD"
        )
    Upload.objects.filter(filename="old.pdf").update(created_at=timezone.now() - timedelta(days=31))
    for username in ("old", "new"):
        identity_services.record_login(username=username, ip="10.0.0.1", succeeded=False)
    LoginAttempt.objects.filter(username="old").update(
        created_at=timezone.now() - timedelta(days=8)
    )

    call_command("purge_expired")

    assert list(Upload.objects.values_list("filename", flat=True)) == ["new.pdf"]
    assert list(LoginAttempt.objects.values_list("username", flat=True)) == ["new"]
