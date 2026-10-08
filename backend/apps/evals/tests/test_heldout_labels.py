from apps.evals.management.commands.run_heldout import labels, markdown
from core.evals.labels import LabelScore
from core.evals.transcript import Label


def test_labels_are_read_per_staff_message() -> None:
    item = {
        "id": "A-1",
        "messages": [
            {"text": "Why did TX-0002 fail?", "expect": "transaction_lookup"},
            {"role": "assistant", "text": "It failed."},
            {"text": "and the other one?", "expect": "ask", "then": "transaction_lookup"},
            "thanks",
        ],
    }
    assert labels(item) == [
        Label("transaction_lookup"),
        Label("ask", "", "transaction_lookup"),
        None,
    ]
    assert labels({"id": "B-1", "message": "hi", "expect": "conversation"}) == [
        Label("conversation")
    ]


def test_the_report_leads_with_the_asking_score_when_labelled() -> None:
    scored = markdown([], LabelScore(clear=4, asked_on_clear=1, decided_right=3, unclear=2))
    assert "| Asks too often (asked on a clear message) | 1 of 4 (25%) |" in scored
    assert "| Asks too rarely (guessed an unclear one) | 2 of 2 (100%) |" in scored
    assert "## Asking" not in markdown([], LabelScore())
