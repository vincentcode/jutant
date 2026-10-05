"""PDF files: the text layer of each page, or OCR for pages that have none (scanned pages).

A scanned page carries its content as an embedded image; OCR reads those images directly, so no
PDF rendering tool is needed.
"""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PageObject, PdfReader

from providers.ocr.base import OcrEngine, OcrUnavailable

SUFFIXES = (".pdf",)


@dataclass(frozen=True)
class ParsedPdf:
    text: str
    pages: int
    ocr_pages: int  # pages read by OCR
    unreadable_pages: int  # pages with no text layer that OCR could not read


def parse(path: Path, ocr: OcrEngine | None = None) -> ParsedPdf:
    reader = PdfReader(str(path))
    texts: list[str] = []
    ocr_pages = unreadable = 0
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if not text and ocr is not None:
            text = _ocr_page(page, ocr)
            ocr_pages += bool(text)
        if not text:
            unreadable += 1
        texts.append(text)
    return ParsedPdf("\n\n".join(t for t in texts if t), len(reader.pages), ocr_pages, unreadable)


def _ocr_page(page: PageObject, ocr: OcrEngine) -> str:
    """The text of the images on a page, or "" if OCR cannot read them."""
    try:
        return "\n".join(
            ocr.extract_text(image.data, f"image/{(image.image.format or 'png').lower()}")
            for image in page.images
        ).strip()
    except OcrUnavailable:
        return ""
