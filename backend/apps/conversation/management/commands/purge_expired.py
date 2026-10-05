"""Delete data kept only for a while: uploaded files' text, and old sign-in attempts.

    python manage.py purge_expired

Uploads are kept JUTANT_UPLOAD_RETENTION_DAYS (they hold customers' ID cards and payslips);
sign-in attempts JUTANT_LOGIN_ATTEMPT_RETENTION_DAYS, well past the lockout window. Docker
Compose runs this every six hours (the `housekeeping` service).
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.conversation import services as conversation_services
from apps.identity import services as identity_services


class Command(BaseCommand):
    help = "Delete uploads and sign-in attempts older than their retention periods."

    def handle(self, *args, **options) -> None:
        now = timezone.now()
        uploads = conversation_services.delete_uploads(
            before=now - timedelta(days=settings.JUTANT_UPLOAD_RETENTION_DAYS)
        )
        attempts = identity_services.delete_login_attempts(
            before=now - timedelta(days=settings.JUTANT_LOGIN_ATTEMPT_RETENTION_DAYS)
        )
        self.stdout.write(f"Deleted {uploads} upload(s) and {attempts} sign-in attempt(s).")
