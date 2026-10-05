"""Load the pack's playbook files into the database.

Run once per deployment. After that, operations staff edit playbooks in the admin, so existing
playbooks are skipped unless `--replace` is given.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.playbooks import services
from core.packs.loader import load_pack


class Command(BaseCommand):
    help = "Load the pack's playbooks into the database."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Overwrite playbooks that already exist, discarding edits made in the admin.",
        )

    def handle(self, *args, **options) -> None:
        pack = load_pack(settings.JUTANT_PACK_PATH)
        for definition in pack.playbooks:
            _, written = services.upsert_playbook(definition=definition, replace=options["replace"])
            state = "loaded" if written else "skipped (exists; use --replace)"
            self.stdout.write(f"{definition.id}: {state}")
