"""How well the assistant decides what staff's messages are about: whether it asks too often
or too rarely, from the audit log.

    python manage.py report_turns              # the last 7 days
    python manage.py report_turns --days 30

Signals to look into, not scores (see `core.evals.turns`). A labelled held-out run measures:
`run_heldout` with `expect` labels.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from apps.audit import selectors
from core.evals.runner import EVAL_CALLER_ID
from core.evals.transcript import HELDOUT_CALLER_ID
from core.evals.turns import render, summarise

EVENTS = ("question_asked", "turn_read", "feature_routed", "clarify_shown", "feedback_given")


class Command(BaseCommand):
    help = "Report how often the assistant asked staff what a message is about, and its guesses."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, **options) -> None:
        since = timezone.now() - timedelta(days=options["days"])
        # Staff's own use only: eval and held-out runs would skew it.
        events = selectors.events_since(
            since=since, names=EVENTS, excluding_staff=(EVAL_CALLER_ID, HELDOUT_CALLER_ID)
        )
        report = summarise((str(e.conversation_id), e.event, e.detail) for e in events)
        self.stdout.write(f"Since {since:%Y-%m-%d %H:%M}\n\n{render(report)}")
