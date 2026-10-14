"""What the assistant can and cannot do for one caller, as facts from the pack.

Given to the conversation, so "what tools do you have?", "can you check balances?" or "why
can't I see customer summaries?" are answered from the pack, not invented: the kinds of help
the caller's role has, what each looks at (the pack's tool labels), the kinds other roles have,
and that the assistant only reads. And how to use the assistant ("how do I attach a file?"):
the platform's own screen, the same for every pack. Assembled in code; short, for a small model.
Every sentence here is the platform's, so none uses a business's words: a pack's own system
prompt adds its examples.
"""

from collections.abc import Iterable, Mapping

from core.types import Caller, Feature

READ_ONLY = (
    "You only read records and documents: you cannot change anything or carry out an action "
    "for staff. For a change, say which kind of help shows its form, approvals or steps."
)
# With requests to send (`core.actions`): prepared, never sent, by the assistant.
PREPARES = (
    "You cannot change anything yourself. Some kinds of help prepare a request (such as asking "
    "for leave): it is shown to staff to check, and sent only when they press Send."
)
# How staff use the assistant: the web client's own controls, by the names it shows.
USING = (
    "How staff use you: they type a question; they choose nothing first, you work out which "
    "kind of help fits and ask when unsure. To read a file, they attach it with the paperclip "
    "(Attach a document), then ask. A procedure shows one step at a time: they answer on its "
    "step card; Stop ends it, Resume continues a paused one. To go back to an earlier subject, "
    "they name it. Answers show their sources and can be rated with the thumbs. Past "
    "conversations are under Conversations, documents under Knowledge, and New conversation "
    "starts afresh."
)


def catalogue(
    features: Iterable[Feature],
    caller: Caller,
    tool_labels: Mapping[str, str],
    leave_out: Iterable[str] = (),
    prepares: bool = False,
) -> str:
    """The facts for `caller`. `leave_out`: features that are not kinds of help (the
    conversation itself). A pack the caller has no role in is not mentioned at all. `prepares`:
    some kinds of help prepare requests to send."""
    skipped = set(leave_out)
    kinds = [f for f in features if f.id not in skipped and caller.in_pack(f.pack) is not None]
    lines = ["The kinds of help you give:"]
    for feature in (f for f in kinds if f.allows_caller(caller)):
        looks = [tool_labels[t] for t in feature.tools if t in tool_labels]
        line = f"- {feature.title}: {feature.description}"
        lines.append(f"{line} It looks at {', '.join(looks)}." if looks else line)
    others = [f for f in kinds if not f.allows_caller(caller)]
    if others:
        lines.append(
            "Not for this staff member's role: "
            + "; ".join(f"{f.title} (for {_roles(f.roles)})" for f in others)
            + "."
        )
    lines += [PREPARES if prepares else READ_ONLY, USING]
    return "\n".join(lines)


def _roles(roles: Iterable[str]) -> str:
    return ", ".join(r.replace("_", " ") for r in roles)
