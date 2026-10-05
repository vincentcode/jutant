"""Pack loading and one failing case per contract rule, on a small pack written to a temp dir."""

import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from core.packs.contract import check
from core.packs.loader import load_pack
from core.types import ToolSpec

MANIFEST = {
    "name": "demo",
    "display_name": "Demo",
    "roles": ["clerk", "lead"],
    "audiences": ["staff"],
    "default_feature": "qa",
    "policy": "demo_pack_policy",
    "mcp_servers": [{"platform": "documents"}, {"pack": "records"}],
    "classifications": [{"label": "internal", "roles": "all"}],
    "features": [
        {
            "id": "qa",
            "template": "document_qa",
            "title": "Q&A",
            "description": "Questions.",
            "prompt": "prompts/qa.md",
            "tools": ["documents.search"],
        },
        {
            "id": "lookup",
            "template": "record_lookup",
            "title": "Lookup",
            "description": "Records.",
            "prompt": "prompts/lookup.md",
            "tools": ["records.get"],
            "roles": ["lead"],
        },
    ],
}
PLAYBOOK = {
    "id": "reset",
    "title": "Reset",
    "description": "Reset something.",
    "steps": [
        {
            "order": 1,
            "title": "Ask",
            "instruction": "Is it on?",
            "audience": ["staff"],
            "expects": "choice",
            "choices": ["yes", "no"],
            "next_on": {"yes": 2, "no": 2},
        },
        {
            "order": 2,
            "title": "Done",
            "instruction": "Done.",
            "audience": ["staff"],
            "expects": "none",
        },
    ],
}
QUESTIONS = [{"id": "q1", "feature": "qa"}, {"id": "q2", "feature": "lookup"}]
SPECS = [ToolSpec(n, n, {"type": "object"}) for n in ("documents.search", "records.get")]
POLICY = """
from core.policy.rules import ALLOW, FunctionRule
RULES = [FunctionRule(t, lambda c, a, r: ALLOW) for t in {tools!r}]
"""


def write_pack(
    root: Path,
    manifest=None,
    playbook=None,
    questions=None,
    ruled=("documents.search", "records.get"),
    prompts=None,
) -> Path:
    (root / "prompts").mkdir(parents=True)
    (root / "playbooks").mkdir()
    (root / "evals").mkdir()
    (root / "pack.yaml").write_text(yaml.safe_dump(manifest or MANIFEST))
    # Written as YAML text so `yes`/`no` keys come back as booleans, as they would by hand.
    (root / "playbooks" / "reset.yaml").write_text(
        yaml.safe_dump(playbook or PLAYBOOK).replace("'yes'", "yes").replace("'no'", "no")
    )
    (root / "evals" / "questions.yaml").write_text(
        yaml.safe_dump(QUESTIONS if questions is None else questions)
    )
    for name, text in (
        prompts or {"system": "Be brief.", "qa": "Search.", "lookup": "Look up."}
    ).items():
        (root / "prompts" / f"{name}.md").write_text(text)
    (root / "demo_pack_policy.py").write_text(textwrap.dedent(POLICY.format(tools=list(ruled))))
    return root


@pytest.fixture
def pack_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(tmp_path / "pack"))
    yield tmp_path / "pack"
    sys.modules.pop("demo_pack_policy", None)


def test_valid_pack_loads_and_passes(pack_root: Path) -> None:
    pack = load_pack(write_pack(pack_root))
    assert check(pack, SPECS) == []
    assert pack.features[1].roles == ("lead",)
    step = pack.playbooks[0].steps[0]
    assert step.choices == ("yes", "no")
    assert step.next_on == {"yes": 2, "no": 2}


def violations(pack_root: Path, specs=SPECS, **overrides) -> list[str]:
    return check(load_pack(write_pack(pack_root, **overrides)), specs)


def with_feature(**changes) -> dict:
    feature = {**MANIFEST["features"][0], **changes}
    return {**MANIFEST, "features": [feature, MANIFEST["features"][1]]}


def test_feature_tool_must_exist(pack_root: Path) -> None:
    found = violations(pack_root, manifest=with_feature(tools=["documents.lookup"]))
    assert "feature qa: tool documents.lookup is not offered by any pack server" in found


def test_every_server_tool_needs_a_rule(pack_root: Path) -> None:
    assert "tool records.get has no access rule" in violations(
        pack_root, ruled=("documents.search",)
    )


def test_roles_must_be_known(pack_root: Path) -> None:
    manifest = {
        **with_feature(roles=["boss"]),
        "classifications": [{"label": "medical", "roles": ["doctor"]}],
        "field_rules": [{"tool": "records.get", "hide": ["x"], "unless_role": ["auditor"]}],
    }
    found = violations(pack_root, manifest=manifest)
    assert "feature qa: unknown role boss" in found
    assert "classification medical: unknown role doctor" in found
    assert "field rule on records.get: unknown role auditor" in found


def test_steps_need_known_audiences(pack_root: Path) -> None:
    steps = [
        {**PLAYBOOK["steps"][0], "audience": []},
        {**PLAYBOOK["steps"][1], "audience": ["robots"]},
    ]
    found = violations(pack_root, playbook={**PLAYBOOK, "steps": steps})
    assert "playbook reset step 1: has no audience" in found
    assert "playbook reset step 2: unknown audience robots" in found


def test_next_on_must_point_to_a_step(pack_root: Path) -> None:
    steps = [{**PLAYBOOK["steps"][0], "next_on": {"yes": 9}}, PLAYBOOK["steps"][1]]
    found = violations(pack_root, playbook={**PLAYBOOK, "steps": steps})
    assert "playbook reset step 1: next_on yes points to missing step 9" in found


def test_default_feature_must_exist(pack_root: Path) -> None:
    found = violations(pack_root, manifest={**MANIFEST, "default_feature": "nope"})
    assert "default_feature nope is not a feature" in found


def test_prompts_must_exist_and_not_be_empty(pack_root: Path) -> None:
    found = violations(pack_root, prompts={"system": "", "qa": "Search."})
    assert "feature lookup: prompt file prompts/lookup.md is missing or empty" in found
    assert "prompts/system.md is missing or empty" in found


def test_extraction_feature_needs_a_schema(pack_root: Path) -> None:
    found = violations(pack_root, manifest=with_feature(template="document_extraction"))
    assert "feature qa: document_extraction needs an extraction schema" in found


def test_every_feature_needs_an_eval_question(pack_root: Path) -> None:
    found = violations(pack_root, questions=[{"id": "q1", "feature": "qa"}])
    assert found == ["feature lookup has no eval question"]
