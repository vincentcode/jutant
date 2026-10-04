"""Implements core.ports.DocumentStore."""

from uuid import UUID

from core.ports import ModelProvider
from core.types import DocumentHit


class DjangoDocumentStore:
    def __init__(self, model: ModelProvider):
        self.model = model  # embeds the query

    async def search(self, query: str, classifications: list[str], limit: int) -> list[DocumentHit]:
        raise NotImplementedError

    async def get_text(self, document_id: UUID, classifications: list[str]) -> str:
        raise NotImplementedError
