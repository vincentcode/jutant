"""The asking report: pickers shown and picked, and the signs of a wrong guess."""

from core.evals.turns import render, summarise

CHOICES = [{"kind": "subject"}, {"kind": "feature"}, {"kind": "new"}]


def asked(text: str, **detail: object) -> tuple[str, str, dict]:
    return ("c1", "question_asked", {"text": text, **detail})


def test_picks_and_ignored_pickers_are_counted() -> None:
    report = summarise(
        [
            asked("why?"),
            ("c1", "clarify_shown", {"reason": "unread", "choices": CHOICES}),
            asked("why?", reply_as="continue", picked=0),  # a pick: not a new message
            asked("and the rate?"),
            ("c1", "clarify_shown", {"reason": "same_or_new", "choices": CHOICES}),
            asked("never mind, the fee"),  # typed past the picker
        ]
    )
    assert report.turns == 3
    assert report.asked == {"unread": 1, "same_or_new": 1}
    assert report.picked == {"subject": 1} and report.picked_first == 1
    assert report.ignored == 1


def test_signs_of_a_wrong_guess_are_counted() -> None:
    report = summarise(
        [
            asked("check TX-0002"),
            ("c1", "turn_read", {"action": "new", "by": "model"}),
            ("c1", "turn_read", {"action": "return", "by": "model"}),  # straight back
            asked("check TX-0002", feature_id="transaction_lookup", reply_as="question"),
            ("c1", "feedback_given", {"rating": "down", "reason": "wrong_feature"}),
            ("c1", "feedback_given", {"rating": "up"}),
        ]
    )
    assert report.resent == 1 and report.quick_returns == 1
    assert (report.thumbs_down, report.wrong_feature) == (1, 1)


def test_a_staff_decision_is_not_a_quick_return() -> None:
    report = summarise(
        [
            ("c1", "turn_read", {"action": "new", "by": "staff"}),
            ("c1", "turn_read", {"action": "return", "by": "staff"}),
        ]
    )
    assert report.quick_returns == 0 and report.decided == {"staff": 2}


def test_the_report_reads_without_any_records() -> None:
    text = render(summarise([]))
    assert "picker shown        0 (0% of messages)" in text
