"""One record's facts, set out in code."""

from core.features.records import document_sources, facts, not_shown, single_record
from core.types import Citation, ToolResult
from tests.builders import doc_result, record_result

PRODUCT = {"code": "SAV-STD", "rate": 2.5, "fees": {"monthly": 0}, "documents": ["ID", "TIN"]}


def test_one_record_is_found_and_flattened() -> None:
    record = single_record([record_result("Product", "SAV-STD", PRODUCT), doc_result("KYC", "4")])
    assert record is not None and record.name == "product SAV-STD"
    assert record.fields == {
        "code": "SAV-STD",
        "rate": "2.5",
        "fees.monthly": "0",
        "documents": "ID, TIN",
    }
    assert "- fees monthly: 0" in facts(record, None)


def test_a_list_two_records_or_an_empty_one_is_not_a_single_record() -> None:
    listing = ToolResult("", True, [{"reference": "TX-1"}], (Citation("record", "Account", "1"),))
    assert single_record([listing]) is None
    two = [record_result("Product", "A", PRODUCT), record_result("Product", "B", PRODUCT)]
    assert single_record(two) is None
    assert single_record([record_result("Product", "A", {})]) is None


def test_not_shown_points_to_the_documents_for_what_generally_applies() -> None:
    record = single_record([record_result("Transaction", "TX-0002", {"status": "failed"})])
    sources = document_sources([doc_result("Error codes", "E51"), doc_result("Error codes", "E51")])
    assert not_shown(record, sources) == (
        "The record for transaction TX-0002 does not show that. "
        "For what generally applies, see Error codes, E51."
    )
