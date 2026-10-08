"""What the assistant can and cannot do, from the pack: for the conversation to answer from."""

from core.features.catalogue import READ_ONLY, catalogue
from tests.builders import FEATURES

LABELS = {"transactions.get_status": "the transfer", "documents.search": "the bank's documents"}


def test_the_catalogue_lists_the_roles_help_what_it_looks_at_and_what_it_cannot() -> None:
    text = catalogue(FEATURES, "teller", LABELS)
    assert "- Transaction lookup: Account activity and why a transfer failed." in text
    assert "It looks at the transfer." in text
    assert "Not for this staff member's role: Customer 360 (for branch manager)." in text
    assert text.endswith(READ_ONLY)


def test_a_role_with_every_kind_of_help_has_no_others_and_the_talk_is_left_out() -> None:
    text = catalogue(FEATURES, "branch_manager", LABELS, leave_out=["policy_qa"])
    assert "Customer 360: Summary of a customer." in text and "Not for" not in text
    assert "Policy Q&A" not in text
