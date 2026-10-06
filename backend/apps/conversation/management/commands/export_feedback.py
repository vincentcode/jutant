"""Write thumbs-down answers as draft eval questions.

    python manage.py export_feedback                     # the last 30 days, to the screen
    python manage.py export_feedback --days 7 --output drafts.yaml

Each draft has the question as staff asked it, the feature that answered and the rater's role,
with what was wrong and the answer given as comments. Before moving a draft into the pack's
`evals/questions.yaml`, fix the feature if the answer was misrouted, add the caller's
attributes (their branch), and say what a right answer must contain (`expect_contains`,
`expect_tool`, `expect_citation`).
"""

import json
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from apps.conversation import selectors

HEADER = """\
# Draft eval questions from thumbs-down answers, exported {when}.
# For each: correct the feature if the answer was misrouted, add attributes (the branch),
# say what a right answer must contain, then move it into the pack's evals/questions.yaml.
"""


class Command(BaseCommand):
    help = "Write thumbs-down answers as draft eval questions."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--days", type=int, default=30, help="ratings from the last N days")
        parser.add_argument("--output", type=Path, help="a file to write; default the screen")

    def handle(self, *args, **options) -> None:
        since = timezone.now() - timedelta(days=options["days"])
        drafts = [HEADER.format(when=timezone.now().date().isoformat())]
        for feedback in selectors.thumbs_down(since=since):
            asked = selectors.question_before(feedback.message)
            if asked is None:
                continue
            drafts.append(draft(feedback, asked.content))
        text = "\n".join(drafts)
        if options["output"]:
            options["output"].write_text(text, encoding="utf-8")
            self.stdout.write(f"Wrote {len(drafts) - 1} draft(s) to {options['output']}")
        else:
            self.stdout.write(text)


def draft(feedback, question: str) -> str:
    """One question in the evals' YAML, with the rating as comments. Strings are written as
    JSON, which YAML reads as quoted strings, so any text is safe."""
    answer = " ".join(feedback.message.content.split())[:200]
    lines = [
        f"# {feedback.get_reason_display() or 'No reason given'}"
        + (f": {one_line(feedback.comment)}" if feedback.comment else ""),
        f"# The answer was: {one_line(answer)}",
        f"- id: fb-{feedback.id.hex[:8]}",
        f"  feature: {feedback.message.feature_id or 'TODO'}",
        f"  role: {feedback.role}",
        "  attributes: {}  # TODO: the caller's branch, e.g. {branch: ACC-01}",
        f"  question: {json.dumps(question, ensure_ascii=False)}",
        "  expect_contains: []  # TODO: facts any right answer must state",
        "",
    ]
    return "\n".join(lines)


def one_line(text: str) -> str:
    return " ".join(text.split())
