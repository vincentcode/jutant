"""Re-chunk and re-embed every indexed document from its stored text.

    python manage.py reindex

Run after changing the chunking or the embedding model. The original files are not needed.
"""

import asyncio

from django.core.management.base import BaseCommand

from ingestion import setup
from ingestion.management.commands.ingest_documents import _close


class Command(BaseCommand):
    help = "Re-chunk and re-embed every indexed document."

    def handle(self, *args, **options) -> None:
        count = asyncio.run(self._reindex())
        self.stdout.write(f"{count} document(s) re-indexed.")

    async def _reindex(self) -> int:
        ingestor = setup.build_ingestor()
        try:
            return await ingestor.reindex()
        finally:
            await _close(ingestor)
