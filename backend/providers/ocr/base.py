"""OcrEngine: reads the text in an image (a scanned page, a photographed ID card)."""

from typing import Protocol


class OcrUnavailable(RuntimeError):
    """The OCR engine is not installed or cannot read this kind of file."""


class OcrEngine(Protocol):
    def extract_text(self, file_bytes: bytes, mime_type: str) -> str: ...
