from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    help = "Ingest every document in a folder."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("folder")
        parser.add_argument("--doc-type", required=True)
        parser.add_argument("--classification", required=True)

    def handle(self, *args, **options) -> None:
        raise NotImplementedError
