"""Builds the Ingestor with the deployment's real model, OCR engine and pack labels."""

from django.conf import settings

from core.packs.loader import load_pack
from ingestion.pipeline import Ingestor
from providers.llm import factory as llm_factory
from providers.ocr.tesseract import TesseractOcr


def build_ingestor() -> Ingestor:
    pack = load_pack(settings.JUTANT_PACK_PATH)
    return Ingestor(
        model=llm_factory.build(settings),
        labels=[c.label for c in pack.manifest.classifications],
        embed_dim=settings.JUTANT_EMBED_DIM,
        ocr=TesseractOcr(),
        document_prefix=settings.JUTANT_EMBED_DOCUMENT_PREFIX,
    )
