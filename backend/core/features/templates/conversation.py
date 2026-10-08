"""`conversation` template.

Talking with staff when no other kind of help is plainly asked for: a greeting, thanks, "what
can you do?", or a request routing could not place. The model sees the kinds of help the
caller's role has (`ctx.offers`, from the pack's features) as tools, one per feature, and
decides itself:

- it calls one: the turn is that feature's (`HandOver`), and the orchestrator answers the
  message with it, prefetch, procedures and citation checks included;
- it cannot tell which of several fits: it calls `ask_which` with them, and staff are shown
  them to pick from (`Clarify`);
- it calls none: it talks, in a few words, with no sources, and the kinds of help are offered
  with its words (`talk`): staff pick one to start it, or just type. Always, not only when
  the words end in a question: a small model asks "how can I help?" in many ways.

A call naming no offered feature is shown to the model once to correct; if it still fails,
staff are offered every kind of help rather than a guess.

It is not a subject of the conversation (`keeps_subject = False`): small talk leaves the
subject staff were on where it was, so the next question is read against it, not pinned to
talking.
"""

from collections.abc import AsyncIterator, Sequence

from core.events import Choice, Clarify, Event, HandOver, TextDelta
from core.features.templates.base import FeatureContext
from core.types import Message, ModelReply, ToolCall, ToolSpec

ASK = "ask_which"
TOOLS = (
    "Your tools are the kinds of help you give. When staff ask for something a tool does, call "
    "that tool: it answers them. If several could fit, or staff need help but do not say with "
    "what, call {ask} with the tools that might fit. Otherwise reply in words."
)
PREFER = "Staff chose the quick action for {title}."
WHICH = "Which of these do you need?"
UNKNOWN = "{name} is not one of your tools. Call one of them, or reply in words."
ATTEMPTS = 2


class ConversationTemplate:
    id = "conversation"
    requires_citation = False
    keeps_subject = False
    # Questions about the assistant itself, the same for every pack: added to a conversation
    # feature's own route examples when the pack loads.
    route_examples = (
        "What tools do you have?",
        "Which kinds of help are there?",
        "Can you make a change on a record for me?",
        "Please do this in the system for me.",
        "How do I use this assistant?",
    )

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        offers = {feature_id: title for feature_id, title, _ in ctx.offers}
        messages = list(ctx.messages)
        tools = _tools(ctx.offers)
        if tools:
            notes = [ctx.catalogue] if ctx.catalogue else []
            notes.append(TOOLS.format(ask=ASK))
            if ctx.prefer in offers:
                notes.append(PREFER.format(title=offers[ctx.prefer]))
            messages.insert(1, Message("system", "\n".join(notes)))
        for _ in range(ATTEMPTS):
            said = ""
            reply = ModelReply(None)
            async for part in ctx.model.stream_chat(messages, tools):
                if isinstance(part, ModelReply):
                    reply = part
                    break
                yield TextDelta(part, continues=bool(said))
                said += part
            if said or not reply.tool_calls:  # words: the answer
                if not said and reply.text:
                    said = reply.text.strip()
                    yield TextDelta(said)
                if offers:  # what it can do, to pick from or not
                    yield Clarify(said.strip(), _choices(list(offers), offers), "talk")
                return
            call = reply.tool_calls[0]
            if call.name in offers:
                yield HandOver(call.name)
                return
            if call.name == ASK and (chosen := _chosen(call, offers)):
                yield TextDelta(WHICH)
                yield Clarify(WHICH, _choices(chosen, offers), "ask_which")
                return
            messages += [
                Message("assistant", reply.text or "", tool_calls=(call,)),
                Message("tool", UNKNOWN.format(name=call.name), tool_call_id=call.id),
            ]
        yield TextDelta(WHICH)  # still no valid call: every kind of help, not a guess
        yield Clarify(WHICH, _choices(list(offers), offers), "no_valid_call")


def _tools(offers: Sequence[tuple[str, str, str]]) -> list[ToolSpec]:
    """One tool per kind of help, taking nothing (the feature reads the message itself), and
    `ask_which`, when there are several to choose from."""
    tools = [
        ToolSpec(feature_id, description, {"type": "object", "properties": {}})
        for feature_id, _, description in offers
    ]
    if len(tools) > 1:
        ids = [t.name for t in tools]
        tools.append(
            ToolSpec(
                ASK,
                "Staff's request could be for several of your tools and you cannot tell which: "
                "show staff those tools to choose from.",
                {
                    "type": "object",
                    "properties": {
                        "options": {"type": "array", "items": {"type": "string", "enum": ids}}
                    },
                    "required": ["options"],
                },
            )
        )
    return tools


def _choices(chosen: Sequence[str], offers: dict[str, str]) -> tuple[Choice, ...]:
    return tuple(Choice("feature", offers[f], feature_id=f) for f in chosen)


def _chosen(call: ToolCall, offers: dict[str, str]) -> list[str]:
    """The offered features `ask_which` names, in its order, once each."""
    options = call.arguments.get("options")
    if isinstance(options, str):
        options = [options]
    if not isinstance(options, list):
        return []
    return list(dict.fromkeys(o for o in options if isinstance(o, str) and o in offers))
