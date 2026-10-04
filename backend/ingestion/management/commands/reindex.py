from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Re-chunk and re-embed every indexed document."

    def handle(self, *args, **options) -> None:
        raise NotImplementedError
