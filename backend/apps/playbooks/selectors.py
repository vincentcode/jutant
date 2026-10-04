"""Every read query for playbooks."""

from uuid import UUID

from apps.playbooks.models import Playbook, PlaybookRun


def get_playbook(*, slug: str) -> Playbook:
    raise NotImplementedError


def list_playbooks() -> list[Playbook]:
    raise NotImplementedError


def active_run(*, conversation_id: UUID) -> PlaybookRun | None:
    raise NotImplementedError
