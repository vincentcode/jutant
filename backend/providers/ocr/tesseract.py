"""Default OCR engine: Tesseract. Reads text from scanned pages with no text layer."""


class TesseractOcr:
    def __init__(self, languages: str = "eng"):
        self.languages = languages

    def extract_text(self, file_bytes: bytes, mime_type: str) -> str:
        raise NotImplementedError
