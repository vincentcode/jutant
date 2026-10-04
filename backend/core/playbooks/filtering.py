"""Picks the playbook steps meant for an audience (staff now, customers later). Pure."""

from core.types import Playbook, PlaybookStep


def steps_for(playbook: Playbook, audience: str) -> tuple[PlaybookStep, ...]:
    """The steps of `playbook` whose audience includes `audience`, in order."""
    raise NotImplementedError
