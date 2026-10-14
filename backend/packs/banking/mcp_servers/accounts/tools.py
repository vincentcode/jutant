"""Tools over the bank's account services: an account's status and holds, its mandate, charges,
standing orders and cheques.

Every tool is registered on a GuardedServer, which checks access and hides fields before data
leaves the server. Each returns the account's branch as its record, so the branch rule can
check the caller's branch against it.
"""

from datetime import date

from core.policy.engine import PolicyEngine
from core.types import Caller, Citation
from mcp_servers.common.guard import GuardedServer, ToolInputError, ToolOutput
from packs.banking.adapters.base import AccountServicesClient, NotFound
from packs.banking.domain import accounts

MAX_CHARGES = 20


def create_server(
    services: AccountServicesClient, engine: PolicyEngine, secret: str
) -> GuardedServer:
    server = GuardedServer("accounts", engine, secret)

    async def branch_of(account_number: str) -> dict[str, str]:
        return {"branch": (await services.get_status(account_number))["branch"]}

    @server.tool(
        "get_status",
        "One account's status: available and ledger balance, holds, liens and blocks, and why "
        "money cannot leave it.",
    )
    async def get_status(caller: Caller, account_number: str) -> ToolOutput:
        status = await services.get_status(account_number.strip())
        return ToolOutput(
            data=accounts.overview(status),
            citations=(Citation("record", "Account", status["account_number"]),),
            record={"branch": status["branch"]},
        )

    @server.tool("get_mandate", "Who may operate one account (its signatories) and who must sign.")
    async def get_mandate(caller: Caller, account_number: str) -> ToolOutput:
        number = account_number.strip()
        record = await branch_of(number)
        return ToolOutput(
            data=await services.get_mandate(number),
            citations=(Citation("record", "Mandate", number),),
            record=record,
        )

    @server.tool(
        "list_charges",
        "Charges and fees taken from one account, newest first, with their fee codes. Dates are "
        "YYYY-MM-DD.",
    )
    async def list_charges(
        caller: Caller,
        account_number: str,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 10,
    ) -> ToolOutput:
        number = account_number.strip()
        record = await branch_of(number)
        filters: dict[str, object] = {"limit": max(1, min(limit, MAX_CHARGES))}
        if from_date:
            filters["from_date"] = _iso_date(from_date)
        if to_date:
            filters["to_date"] = _iso_date(to_date)
        rows = await services.list_charges(number, **filters)
        return ToolOutput(
            data={"account_number": number, **accounts.charges(rows)},
            citations=(Citation("record", "Charges", number),),
            record=record,
        )

    @server.tool(
        "list_standing_orders",
        "Standing orders on one account: beneficiary, amount, next run, and whether the last "
        "run failed and why.",
    )
    async def list_standing_orders(caller: Caller, account_number: str) -> ToolOutput:
        number = account_number.strip()
        record = await branch_of(number)
        rows = await services.list_standing_orders(number)
        return ToolOutput(
            data={"account_number": number, **accounts.standing_orders(rows)},
            citations=(Citation("record", "Standing orders", number),),
            record=record,
        )

    @server.tool(
        "get_cheque",
        "One cheque on an account by its number: paid, in clearing, stopped or returned, and why.",
    )
    async def get_cheque(caller: Caller, account_number: str, cheque_number: str) -> ToolOutput:
        number, cheque = account_number.strip(), cheque_number.strip()
        record = await branch_of(number)
        try:
            found = await services.get_cheque(number, cheque)
        except NotFound:
            # Said as data, with the account's branch: on another branch's account the guard
            # refuses it, rather than "not found" telling the caller about that account.
            return ToolOutput(
                data={"account_number": number, "cheque_number": cheque, "found": False},
                record=record,
            )
        return ToolOutput(
            data=accounts.cheque(found),
            citations=(Citation("record", "Cheque", f"{number}/{cheque}"),),
            record=record,
        )

    return server


def _iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        raise ToolInputError(f"{value!r} is not a date; use YYYY-MM-DD") from None
