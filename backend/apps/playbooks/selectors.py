"""Every read query for playbooks. Only active playbooks are offered to staff."""

from uuid import UUID

from apps.playbooks.models import Playbook, PlaybookRun


def get_playbook(*, slug: str) -> Playbook | None:
    return Playbook.objects.prefetch_related("steps").filter(slug=slug, is_active=True).first()


def list_playbooks() -> list[Playbook]:
    return list(Playbook.objects.prefetch_related("steps").filter(is_active=True).order_by("title"))


def active_run(*, conversation_id: UUID) -> PlaybookRun | None:
    return PlaybookRun.objects.filter(
        conversation_id=conversation_id, status=PlaybookRun.Status.ACTIVE
    ).first()
