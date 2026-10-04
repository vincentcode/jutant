"""ToolCatalog: the tools every configured MCP server offers, named `<server>.<tool>`."""

from core.ports import ToolClient
from core.types import ToolSpec


class ToolCatalog:
    def __init__(self, client: ToolClient):
        self.client = client
        self._specs: dict[str, ToolSpec] = {}

    async def load(self) -> None:
        """Load specs at start-up. Names are `<server>.<tool>`."""
        raise NotImplementedError

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def specs_for(self, names: tuple[str, ...]) -> list[ToolSpec]:
        raise NotImplementedError
