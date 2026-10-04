"""Load the pack's playbook YAML files into the tables.

After that, operations staff edit them in the admin.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load the loaded pack's playbooks into the database."

    def handle(self, *args, **options) -> None:
        raise NotImplementedError
