"""ActionService: proposals made in a turn, confirmed or cancelled by the person who asked.

`propose` keeps a draft the pack's propose tool returned and starts its clock. `confirm` is
called by the client, never by the model: it claims the proposal (only its caller's, only while
it waits, only once), calls the action's perform tool with the draft's arguments as they were
shown plus `request_id` (the proposal's id, so a client system that sees it twice does it once),
and keeps the outcome. A system that did not answer leaves the proposal waiting, to send again;
a refusal ends it. The outcome is added to the conversation as a note the model reads later
("what's the status of my leave request?") and staff do not see twice.
"""

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from core.actions.drafts import read_outcome
from core.actions.types import Action, Draft, Proposal
from core.ports import ActionStore, AuditSink, ConversationStore, ToolClient
from core.types import Caller, Message, ToolCall

REQUEST_ID = "request_id"  # the argument every perform tool takes, to do a request once
NOT_ANSWERED = "The system did not answer, so nothing was sent. Try again in a moment."
FAILED = {
    "denied": "You are not allowed to do this.",
    "not_found": "What this request refers to no longer exists.",
    "invalid_arguments": "The system refused the request as it was.",
}


class ActionService:
    def __init__(
        self,
        actions: Iterable[Action],
        store: ActionStore,
        tools: ToolClient,
        conversations: ConversationStore,
        audit: AuditSink,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.actions = {a.id: a for a in actions}
        self.store = store
        self.tools = tools
        self.conversations = conversations
        self.audit = audit
        self.now = now

    def proposed_by(self, tool: str) -> Action | None:
        """The action whose propose tool this is, if any."""
        return next((a for a in self.actions.values() if a.propose == tool), None)

    async def propose(
        self, caller: Caller, conversation_id: UUID, action: Action, draft: Draft
    ) -> Proposal:
        now = self.now()
        proposal = Proposal(
            id=uuid4(),
            action_id=action.id,
            title=action.title,
            icon=action.icon,
            conversation_id=conversation_id,
            caller_id=caller.id,
            draft=draft,
            expires_at=now + timedelta(seconds=action.expires_s),
            created_at=now,
        )
        await self.store.create(proposal)
        await self.audit.record(caller, "action_proposed", _detail(proposal))
        return proposal

    async def confirm(self, caller: Caller, proposal_id: UUID) -> Proposal:
        proposal = await self.store.claim(proposal_id, caller.id, self.now())
        action = self.actions.get(proposal.action_id)
        if action is None or not action.allows(caller.role):
            done = await self.store.finish(proposal.id, "failed", outcome=FAILED["denied"])
            await self.audit.record(caller, "action_failed", {**_detail(done), "error": "denied"})
            return done
        arguments = {**proposal.draft.submit, REQUEST_ID: str(proposal.id)}
        result = await self.tools.call(
            caller, ToolCall(f"action-{proposal.id}", action.perform, arguments)
        )
        if result.ok:
            reference, status = read_outcome(result.data)
            done = await self.store.finish(proposal.id, "sent", reference, status)
            await self.conversations.append(
                proposal.conversation_id, Message("system", _note(done))
            )
            await self.audit.record(caller, "action_confirmed", _detail(done))
            return done
        error = result.error or "upstream_error"
        if error == "upstream_error":
            done = await self.store.finish(proposal.id, "proposed", outcome=NOT_ANSWERED)
        else:
            done = await self.store.finish(proposal.id, "failed", outcome=FAILED[error])
        await self.audit.record(caller, "action_failed", {**_detail(done), "error": error})
        return done

    async def cancel(self, caller: Caller, proposal_id: UUID) -> Proposal:
        proposal = await self.store.cancel(proposal_id, caller.id, self.now())
        await self.audit.record(caller, "action_cancelled", _detail(proposal))
        return proposal

    async def for_conversation(self, caller: Caller, conversation_id: UUID) -> list[Proposal]:
        """The conversation's proposals, oldest first; those past their time shown as expired."""
        now = self.now()
        return [
            replace(p, status="expired") if p.status == "proposed" and p.expires_at <= now else p
            for p in await self.store.for_conversation(conversation_id, caller.id)
        ]


def _note(proposal: Proposal) -> str:
    """What the model reads later: "Sent: Leave request LV-2026-00318 (Annual leave, 10-14 Nov
    2026). Status: Waiting for your manager." """
    what = f"{proposal.title} {proposal.reference}".strip()
    about = f" ({proposal.draft.summary})" if proposal.draft.summary else ""
    status = f" Status: {proposal.outcome}." if proposal.outcome else ""
    return f"Sent: {what}{about}.{status}"


def _detail(proposal: Proposal) -> dict[str, object]:
    return {
        "proposal_id": str(proposal.id),
        "action": proposal.action_id,
        "conversation_id": str(proposal.conversation_id),
        "status": proposal.status,
        "reference": proposal.reference,
    }
