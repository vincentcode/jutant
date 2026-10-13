"""Tools over the bank's card management system: a customer's cards, and one card with its
recent attempts and why they were declined.

Every tool is registered on a GuardedServer, which checks access and hides fields before data
leaves the server. Each returns the branch it belongs to as its record, so the branch rule can
check the caller's branch against it. Card numbers are only ever shown masked.
"""

from core.policy.engine import PolicyEngine
from core.types import Caller, Citation
from mcp_servers.common.guard import GuardedServer, ToolOutput
from packs.banking.adapters.base import CardsClient, CoreBankingClient
from packs.banking.domain import cards as card_facts

RECENT = 10


def create_server(
    cards: CardsClient, banking: CoreBankingClient, engine: PolicyEngine, secret: str
) -> GuardedServer:
    server = GuardedServer("cards", engine, secret)

    @server.tool("list_cards", "A customer's cards: masked number, type, status and block reason.")
    async def list_cards(caller: Caller, customer_number: str) -> ToolOutput:
        number = customer_number.strip().upper()
        customer = await banking.get_customer(number)
        return ToolOutput(
            data={"customer_number": number, **card_facts.cards(await cards.list_cards(number))},
            citations=(Citation("record", "Customer cards", number),),
            record={"branch": customer["branch"]},
        )

    @server.tool(
        "get_card",
        "One card by its id: status, block reason, limits and settings, and its recent "
        "attempts with the decline codes.",
    )
    async def get_card(caller: Caller, card_id: str) -> ToolOutput:
        card_number = card_id.strip().upper()
        record = await cards.get_card(card_number)
        attempts = await cards.recent_authorisations(card_number, RECENT)
        return ToolOutput(
            data=card_facts.card(record, attempts),
            citations=(Citation("record", "Card", card_number),),
            record={"branch": record["branch"]},
        )

    return server
