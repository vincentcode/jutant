"""Ingest every supported document in a folder.

    python manage.py ingest_documents /data/policies --doc-type policy --classification internal

Each file is reported as indexed, replaced, skipped or failed; one bad file does not stop the
rest. The command fails at the end if any file failed.
"""

import asyncio
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from ingestion import setup
from ingestion.pipeline import SUPPORTED, IngestError, Ingestor


class Command(BaseCommand):
    help = "Ingest every supported document in a folder into the search index."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("folder", type=Path)
        parser.add_argument("--doc-type", required=True, help="e.g. policy, circular, procedure")
        parser.add_argument(
            "--classification", required=True, help="one of the pack's labels, e.g. internal"
        )
        parser.add_argument("--recursive", action="store_true", help="include sub-folders")

    def handle(self, *args, **options) -> None:
        folder: Path = options["folder"]
        if not folder.is_dir():
            raise CommandError(f"{folder} is not a folder")
        pattern = "**/*" if options["recursive"] else "*"
        files = sorted(p for p in folder.glob(pattern) if p.suffix.lower() in SUPPORTED)
        if not files:
            raise CommandError(f"no {', '.join(SUPPORTED)} files in {folder}")
        failed = asyncio.run(self._ingest_all(setup.build_ingestor(), files, options))
        self.stdout.write(f"{len(files) - failed} of {len(files)} files ingested.")
        if failed:
            raise CommandError(f"{failed} file(s) failed")

    async def _ingest_all(self, ingestor: Ingestor, files: list[Path], options) -> int:
        failed = 0
        try:
            for path in files:
                try:
                    result = await ingestor.ingest(
                        path,
                        doc_type=options["doc_type"],
                        classification=options["classification"],
                    )
                except IngestError as exc:
                    failed += 1
                    self.stderr.write(f"failed    {path.name}: {exc}")
                    continue
                except Exception as exc:  # a bad file must not stop the rest
                    failed += 1
                    self.stderr.write(f"failed    {path.name}: {type(exc).__name__}: {exc}")
                    continue
                detail = f" ({result.note})" if result.note else ""
                chunks = f", {result.chunks} chunks" if result.chunks else ""
                self.stdout.write(f"{result.status:<9} {path.name}{chunks}{detail}")
        finally:
            await _close(ingestor)
        return failed


async def _close(ingestor: Ingestor) -> None:
    close = getattr(ingestor.model, "close", None)
    if close is not None:
        await close()
