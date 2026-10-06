"""load_pack(path) -> Pack: reads a pack folder into the core's types.

Reads `pack.yaml`, the prompt files, the playbook files and the eval questions, and imports the
pack's policy module for its RULES. A missing prompt file loads as empty text rather than
failing here, so the contract check can report every problem at once.
"""

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.packs.manifest import PackManifest
from core.policy.rules import FieldRule, Rule
from core.types import ArgumentSource, Feature, Playbook, PlaybookStep, Prefetch, StepLookup

SYSTEM_PROMPT = "prompts/system.md"


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

    @property
    def extraction_schemas(self) -> dict[str, list[str]]:
        return {s.type: list(s.fields) for s in self.manifest.extraction_schemas}

    def readable_classifications(self, role: str) -> list[str]:
        """The document labels a role may read; search is always filtered to these."""
        return [
            c.label for c in self.manifest.classifications if c.roles == "all" or role in c.roles
        ]


def load_pack(path: str | Path) -> Pack:
    root = Path(path)
    manifest = PackManifest.model_validate(_read_yaml(root / "pack.yaml"))
    features = tuple(
        Feature(
            id=f.id,
            template=f.template,
            title=f.title,
            description=f.description,
            prompt=_read_text(root / f.prompt),
            tools=tuple(f.tools),
            roles=tuple(f.roles),
            route_patterns=tuple(f.route.patterns),
            route_examples=tuple(f.route.examples),
            suggestions=tuple(f.suggestions),
            prefetch=tuple(
                Prefetch(
                    p.tool,
                    {
                        name: ArgumentSource(a.question, a.match, a.value)
                        for name, a in p.arguments.items()
                    },
                )
                for p in f.prefetch
            ),
        )
        for f in manifest.features
    )
    policy = importlib.import_module(manifest.policy)
    field_rules = tuple(
        FieldRule(r.tool, tuple(r.hide), tuple(r.unless_role)) for r in manifest.field_rules
    )
    playbooks = tuple(_playbook(_read_yaml(p)) for p in sorted((root / "playbooks").glob("*.yaml")))
    questions_file = root / "evals" / "questions.yaml"
    questions = _read_yaml(questions_file) if questions_file.exists() else []
    return Pack(
        path=root,
        manifest=manifest,
        system_prompt=_read_text(root / SYSTEM_PROMPT),
        features=features,
        playbooks=playbooks,
        rules=tuple(policy.RULES),
        field_rules=field_rules,
        eval_questions=tuple(questions or ()),
    )


def _read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def _playbook(data: dict[str, Any]) -> Playbook:
    return Playbook(
        id=str(data["id"]),
        title=str(data["title"]),
        description=str(data.get("description", "")),
        steps=tuple(_step(s) for s in data.get("steps", [])),
    )


def _step(data: dict[str, Any]) -> PlaybookStep:
    return PlaybookStep(
        order=int(data["order"]),
        title=str(data["title"]),
        instruction=str(data["instruction"]),
        audience=tuple(str(a) for a in data.get("audience") or ()),
        expects=data.get("expects", "confirm"),
        choices=tuple(_key(c) for c in data.get("choices") or ()),
        next_on={_key(k): int(v) for k, v in (data.get("next_on") or {}).items()},
        lookup=_lookup(data["lookup"]) if data.get("lookup") else None,
        answer_from=str(data["answer_from"]) if data.get("answer_from") else None,
    )


def _lookup(data: dict[str, Any]) -> StepLookup:
    return StepLookup(
        tool=str(data["tool"]),
        argument=str(data["argument"]),
        pattern=str(data["pattern"]) if data.get("pattern") else None,
    )


def _key(value: Any) -> str:
    """YAML reads bare yes/no as booleans; turn them back into the words the author wrote."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)
