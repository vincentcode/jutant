"""Picks the playbook steps meant for an audience (staff now, customers later). Pure."""

from core.types import Playbook, PlaybookStep


def steps_for(playbook: Playbook, audience: str) -> tuple[PlaybookStep, ...]:
    """The steps of `playbook` whose audience includes `audience`, in order."""
    return tuple(
        sorted((s for s in playbook.steps if audience in s.audience), key=lambda s: s.order)
    )


def next_step(
    steps: tuple[PlaybookStep, ...], current: PlaybookStep, answer: str
) -> PlaybookStep | None:
    """The step after `current` given the answer, or None when the playbook is finished.

    A `next_on` entry for the answer wins; otherwise the next step in order. If the target step is
    not visible to this audience, the next visible step after it is used instead.
    """
    target = current.next_on.get(answer)
    if target is None:
        return next((s for s in steps if s.order > current.order), None)
    return next((s for s in steps if s.order >= target), None)
