"""Reads the text of a file staff upload into a conversation, for extraction or summarising.

Uses the same parsers as ingestion; photos and scans (PNG, JPEG, TIFF) go straight to OCR. The
text is used in that conversation only and is never added to the search index.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from ingestion.parsers import docx, pdf, text
from providers.ocr.base import OcrEngine, OcrUnavailable

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
ACCEPTED = (*text.SUFFIXES, *docx.SUFFIXES, *pdf.SUFFIXES, *IMAGE_TYPES)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class UploadError(Exception):
    """The upload cannot be read; the message says why in plain language."""


@dataclass(frozen=True)
class ReadUpload:
    text: str
    note: str = ""  # how it was read, when staff should know: "2 of 3 pages read by OCR"


def read_upload(filename: str, data: bytes, ocr: OcrEngine | None) -> ReadUpload:
    """The text of an uploaded file, and how it was read. Raises UploadError if it cannot be
    read, saying what to try instead."""
    notes: list[str] = []
    text = extract_text(filename, data, ocr, notes)
    if Path(filename).suffix.lower() in IMAGE_TYPES:
        notes.append("read from an image by OCR: check names and numbers")
    return ReadUpload(text, "; ".join(n for n in notes if n))


def extract_text(
    filename: str, data: bytes, ocr: OcrEngine | None, notes: list[str] | None = None
) -> str:
    """The text of an uploaded file. Raises UploadError if it cannot be read."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ACCEPTED:
        raise UploadError(f"{filename}: unsupported file type (use {', '.join(ACCEPTED)})")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(f"{filename}: larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

    if suffix in IMAGE_TYPES:
        if ocr is None:
            raise UploadError(f"{filename}: reading images needs OCR, which is not available")
        try:
            body = ocr.extract_text(data, IMAGE_TYPES[suffix])
        except OcrUnavailable as exc:
            raise UploadError(f"{filename}: {exc}") from exc
    else:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / f"upload{suffix}"
            path.write_bytes(data)
            body = _parse(path, filename, ocr, notes)

    body = body.strip()
    if not body:
        hint = (
            " If it is a photo or a scan, try a sharper, straight, well-lit picture."
            if suffix in IMAGE_TYPES or suffix in pdf.SUFFIXES
            else ""
        )
        raise UploadError(f"{filename}: no text could be read.{hint}")
    return body


def _parse(path: Path, filename: str, ocr: OcrEngine | None, notes: list[str] | None) -> str:
    suffix = path.suffix
    try:
        if suffix in text.SUFFIXES:
            return text.parse(path)
        if suffix in docx.SUFFIXES:
            return docx.parse(path)
        parsed = pdf.parse(path, ocr)
        if notes is not None:
            notes.append(_pdf_note(parsed))
        return parsed.text
    except Exception as exc:  # a corrupt file is the uploader's problem, not a server error
        raise UploadError(f"{filename}: could not be read ({type(exc).__name__})") from exc


def _pdf_note(parsed: pdf.ParsedPdf) -> str:
    parts = []
    if parsed.ocr_pages:
        parts.append(f"{parsed.ocr_pages} of {parsed.pages} pages read by OCR")
    if parsed.unreadable_pages:
        parts.append(f"{parsed.unreadable_pages} of {parsed.pages} pages could not be read")
    return "; ".join(parts)
