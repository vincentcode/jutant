"""Tools over the bank's lending system: a customer's loans and deposits, one loan with its
arrears and schedule, one fixed deposit.

Every tool is registered on a GuardedServer, which checks access and hides fields before data
leaves the server. Each returns the branch it belongs to as its record, so the branch rule can
check the caller's branch against it.
"""

from core.policy.engine import PolicyEngine
from core.types import Caller, Citation
from mcp_servers.common.guard import GuardedServer, ToolOutput
from packs.banking.adapters.base import CoreBankingClient, LendingClient
from packs.banking.domain import lending


def create_server(
    loans: LendingClient, banking: CoreBankingClient, engine: PolicyEngine, secret: str
) -> GuardedServer:
    server = GuardedServer("lending", engine, secret)

    @server.tool(
        "list_facilities",
        "A customer's loans and fixed deposits, with totals outstanding and in arrears.",
    )
    async def list_facilities(caller: Caller, customer_number: str) -> ToolOutput:
        number = customer_number.strip().upper()
        customer = await banking.get_customer(number)
        data = lending.facilities(await loans.list_loans(number), await loans.list_deposits(number))
        return ToolOutput(
            data={"customer_number": number, **data},
            citations=(Citation("record", "Customer facilities", number),),
            record={"branch": customer["branch"]},
        )

    @server.tool(
        "get_loan",
        "One loan by its number: balance, arrears and days past due, next instalment, and the "
        "overdue instalments.",
    )
    async def get_loan(caller: Caller, loan_id: str) -> ToolOutput:
        loan_number = loan_id.strip().upper()
        record = await loans.get_loan(loan_number)
        schedule = await loans.get_schedule(loan_number)
        return ToolOutput(
            data=lending.loan(record, schedule),
            citations=(Citation("record", "Loan", loan_number),),
            record={"branch": record["branch"]},
        )

    @server.tool(
        "get_deposit",
        "One fixed deposit by its number: rate, maturity date and amount, interest earned, "
        "rollover and early withdrawal penalty.",
    )
    async def get_deposit(caller: Caller, deposit_id: str) -> ToolOutput:
        deposit_number = deposit_id.strip().upper()
        record = await loans.get_deposit(deposit_number)
        return ToolOutput(
            data=lending.deposit(record),
            citations=(Citation("record", "Deposit", deposit_number),),
            record={"branch": record["branch"]},
        )

    return server
