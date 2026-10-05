"""ToolCatalog: the tools every configured MCP server offers, named `<server>.<tool>`."""

from core.ports import ToolClient
from core.types import ToolSpec


class ToolCatalog:
    def __init__(self, client: ToolClient):
        self.client = client
        self._specs: dict[str, ToolSpec] = {}

    async def load(self) -> None:
        """Load specs at start-up. The client already prefixes names with the server name."""
        self._specs = {spec.name: spec for spec in await self.client.list_tools()}

    @property
    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def specs_for(self, names: tuple[str, ...]) -> list[ToolSpec]:
        """The specs for `names`, in that order. Names the catalog does not know are skipped."""
        return [self._specs[name] for name in names if name in self._specs]
