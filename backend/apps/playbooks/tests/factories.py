"""factory_boy factories that create `apps.playbooks` rows for tests."""

from core.types import Playbook, PlaybookStep

BLOCKED_CARD = Playbook(
    "blocked_card",
    "Blocked card",
    "Card is blocked.",
    (
        PlaybookStep(1, "Verify", "Verify the customer.", ("staff",)),
        PlaybookStep(
            2,
            "Reason",
            "Which reason?",
            ("staff",),
            "choice",
            ("wrong_pin", "fraud_hold"),
            {"wrong_pin": 3, "fraud_hold": 3},
        ),
        PlaybookStep(3, "Close", "Close.", ("staff", "customer"), "none"),
    ),
)
