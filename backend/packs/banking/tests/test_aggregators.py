"""The customer summary is assembled, and every figure computed, in code."""

from packs.banking.adapters.fake import FakeCoreBanking, FakeServiceCatalog
from packs.banking.mcp_servers.services.aggregators import customer_summary


async def summary(number: str) -> dict:
    return await customer_summary(FakeCoreBanking(), FakeServiceCatalog(), number)


async def test_balances_are_totalled_across_accounts() -> None:
    result = await summary("C1001")
    assert result["account_count"] == 2
    assert result["total_balance"] == {"GHS": "6021.25"}  # 4520.75 + 1500.50, exactly
    assert [a["account_number"] for a in result["accounts"]] == ["0011223344", "0011223355"]


async def test_recent_activity_spans_accounts_newest_first() -> None:
    result = await summary("C1001")
    assert [t["reference"] for t in result["recent_transactions"]] == [
        "TX-0003",
        "TX-0002",
        "TX-0001",
        "TX-0004",
    ]
    assert result["recent_transactions"][-1]["account_number"] == "0011223355"
    assert result["failed_transactions"] == ["TX-0002"]


async def test_requests_flags_and_dormant_accounts() -> None:
    ama = await summary("C1001")
    assert ama["open_requests"] == [
        {"id": "REQ-77", "type": "card_replacement", "status": "in_progress"}
    ]
    assert (ama["flags"], ama["dormant_accounts"]) == ([], [])
    kofi = await summary("C1002")
    assert kofi["flags"] == ["kyc_review_due"]
    assert kofi["dormant_accounts"] == ["0099887766"]
    assert kofi["open_requests"] == []
    assert kofi["branch"] == "KSI-02"
