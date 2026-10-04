from typing import Protocol


class OcrEngine(Protocol):
    def extract_text(self, file_bytes: bytes, mime_type: str) -> str: ...
