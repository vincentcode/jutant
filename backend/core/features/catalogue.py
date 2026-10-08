"""What the assistant can and cannot do for one caller, as facts from the pack.

Given to the conversation, so "what tools do you have?", "can you check balances?" or "why
can't I see customer summaries?" are answered from the pack, not invented: the kinds of help
the caller's role has, what each looks at (the pack's tool labels), the kinds other roles have,
and that the assistant only reads. Assembled in code; short, for a small model.
"""

from collections.abc import Iterable, Mapping

from core.types import Feature

READ_ONLY = (
    "You only read records and documents: you cannot change anything, make a payment or act on "
    "an account. For a change, say which kind of help shows its form, approvals or steps."
)


def catalogue(
    features: Iterable[Feature],
    role: str,
    tool_labels: Mapping[str, str],
    leave_out: Iterable[str] = (),
) -> str:
    """The facts for a caller with `role`. `leave_out`: features that are not kinds of help
    (the conversation itself)."""
    skipped = set(leave_out)
    kinds = [f for f in features if f.id not in skipped]
    lines = ["The kinds of help you give:"]
    for feature in (f for f in kinds if f.allows(role)):
        looks = [tool_labels[t] for t in feature.tools if t in tool_labels]
        line = f"- {feature.title}: {feature.description}"
        lines.append(f"{line} It looks at {', '.join(looks)}." if looks else line)
    others = [f for f in kinds if not f.allows(role)]
    if others:
        lines.append(
            "Not for this staff member's role: "
            + "; ".join(f"{f.title} (for {_roles(f.roles)})" for f in others)
            + "."
        )
    lines.append(READ_ONLY)
    return "\n".join(lines)


def _roles(roles: Iterable[str]) -> str:
    return ", ".join(r.replace("_", " ") for r in roles)
