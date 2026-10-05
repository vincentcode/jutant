"""Default OCR engine: Tesseract. Reads text from scanned pages with no text layer.

Needs the `tesseract` program, which the backend Docker image installs. Takes image bytes
(PNG, JPEG, TIFF...); a scanned PDF is read by passing in the images embedded in its pages.
"""

import io

import pytesseract
from PIL import Image, UnidentifiedImageError

from providers.ocr.base import OcrUnavailable


class TesseractOcr:
    def __init__(self, languages: str = "eng"):
        self.languages = languages  # e.g. "eng+fra"

    def extract_text(self, file_bytes: bytes, mime_type: str) -> str:
        try:
            image = Image.open(io.BytesIO(file_bytes))
        except UnidentifiedImageError as exc:
            raise OcrUnavailable(f"cannot read a {mime_type} file as an image") from exc
        try:
            text = pytesseract.image_to_string(image, lang=self.languages)
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrUnavailable("tesseract is not installed") from exc
        return text.strip()
