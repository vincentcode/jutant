"""Reads the text of a file staff upload into a conversation, for extraction or summarising.

Uses the same parsers as ingestion; photos and scans (PNG, JPEG, TIFF) go straight to OCR. The
text is used in that conversation only and is never added to the search index.
"""

import tempfile
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


def extract_text(filename: str, data: bytes, ocr: OcrEngine | None) -> str:
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
            body = _parse(path, filename, ocr)

    body = body.strip()
    if not body:
        raise UploadError(f"{filename}: no text found")
    return body


def _parse(path: Path, filename: str, ocr: OcrEngine | None) -> str:
    suffix = path.suffix
    try:
        if suffix in text.SUFFIXES:
            return text.parse(path)
        if suffix in docx.SUFFIXES:
            return docx.parse(path)
        return pdf.parse(path, ocr).text
    except Exception as exc:  # a corrupt file is the uploader's problem, not a server error
        raise UploadError(f"{filename}: could not be read ({type(exc).__name__})") from exc
