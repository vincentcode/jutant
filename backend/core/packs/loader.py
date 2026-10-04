"""load_pack(path) -> Pack.

Reads `pack.yaml`, resolves prompt files, imports the policy module and reads playbooks.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.packs.manifest import PackManifest
from core.policy.rules import FieldRule, Rule
from core.types import Feature, Playbook


@dataclass(frozen=True)
class Pack:
    path: Path
    manifest: PackManifest
    system_prompt: str
    features: tuple[Feature, ...]
    playbooks: tuple[Playbook, ...]
    rules: tuple[Rule, ...]
    field_rules: tuple[FieldRule, ...]
    eval_questions: tuple[dict[str, Any], ...] = ()


def load_pack(path: str | Path) -> Pack:
    raise NotImplementedError
