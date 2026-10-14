"""Builds the Ingestor with the deployment's real model, OCR engine and the packs' labels."""

from django.conf import settings

from core.packs.loader import load_pack
from ingestion.pipeline import Ingestor
from providers.llm import factory as llm_factory
from providers.ocr.tesseract import TesseractOcr


def pack_names() -> list[str]:
    return [load_pack(path).manifest.name for path in settings.JUTANT_PACKS]


def build_ingestor() -> Ingestor:
    packs = [load_pack(path) for path in settings.JUTANT_PACKS]
    return Ingestor(
        model=llm_factory.build(settings),
        labels=sorted({c.label for p in packs for c in p.manifest.classifications}),
        embed_dim=settings.JUTANT_EMBED_DIM,
        ocr=TesseractOcr(),
        document_prefix=settings.JUTANT_EMBED_DOCUMENT_PREFIX,
    )
