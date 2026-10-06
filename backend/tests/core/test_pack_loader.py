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


SEARCH_SPECS = [
    ToolSpec("documents.search", "", {"type": "object", "properties": {"query": {}}}),
    ToolSpec("records.get", "", {"type": "object"}),
]


def test_routing_and_prefetch_load(pack_root: Path) -> None:
    manifest = with_feature(
        route={"patterns": [r"\bQ-\d+\b"], "examples": ["What is the rule?"]},
        prefetch=[{"tool": "documents.search", "arguments": {"query": {"question": True}}}],
    )
    pack = load_pack(write_pack(pack_root, manifest=manifest))
    assert check(pack, SEARCH_SPECS) == []
    qa = pack.features[0]
    assert qa.route_patterns == (r"\bQ-\d+\b",) and qa.route_examples == ("What is the rule?",)
    assert qa.prefetch[0].tool == "documents.search"
    assert qa.prefetch[0].arguments["query"].question is True


def test_route_patterns_must_be_valid(pack_root: Path) -> None:
    found = violations(pack_root, manifest=with_feature(route={"patterns": ["(unclosed"]}))
    assert any(p.startswith("feature qa: route pattern '(unclosed'") for p in found)


@pytest.mark.parametrize(
    ("prefetch", "problem"),
    [
        (
            {"tool": "records.get", "arguments": {"query": {"question": True}}},
            "feature qa: prefetch records.get: the feature's tools do not include it",
        ),
        (
            {"tool": "documents.search", "arguments": {"q": {"question": True}}},
            "feature qa: prefetch documents.search: the tool takes no argument q",
        ),
        (
            {"tool": "documents.search", "arguments": {"query": {"match": r"(A)(B)"}}},
            "feature qa: prefetch documents.search: argument query: has 2 groups; use at most 1",
        ),
    ],
    ids=["tool outside the feature", "unknown argument", "two groups"],
)
def test_prefetch_must_fit_the_feature_and_tool(pack_root: Path, prefetch, problem) -> None:
    found = violations(pack_root, SEARCH_SPECS, manifest=with_feature(prefetch=[prefetch]))
    assert problem in found


def test_a_prefetch_argument_has_exactly_one_source(pack_root: Path) -> None:
    prefetch = {"tool": "documents.search", "arguments": {"query": {"question": True, "value": 1}}}
    with pytest.raises(ValueError, match="exactly one"):
        load_pack(write_pack(pack_root, manifest=with_feature(prefetch=[prefetch])))


def test_a_branch_must_not_run_on_into_another_branch(pack_root: Path) -> None:
    # The failed-transfer procedure as first written: "failed" went to step 2, which had no
    # next_on, so it carried on into step 3, the advice for pending transfers.
    playbook = {
        **PLAYBOOK,
        "steps": [
            {
                "order": 1,
                "title": "Status",
                "instruction": "Which status?",
                "audience": ["staff"],
                "expects": "choice",
                "choices": ["failed", "pending"],
                "next_on": {"failed": 2, "pending": 3},
            },
            {
                "order": 2,
                "title": "Explain",
                "instruction": "Explain the failure.",
                "audience": ["staff"],
            },
            {
                "order": 3,
                "title": "Timing",
                "instruction": "Pending transfers settle soon.",
                "audience": ["staff"],
            },
        ],
    }
    found = violations(pack_root, playbook=playbook)
    assert (
        "playbook reset step 2: the 'failed' branch of step 1 runs on into step 3, "
        "the 'pending' branch; end it with next_on"
    ) in found


GUIDED = {
    "id": "help",
    "template": "guided_playbook",
    "title": "Help",
    "description": "Procedures.",
    "prompt": "prompts/qa.md",
    "tools": ["records.get"],
}
RECORD_SPECS = [
    ToolSpec("documents.search", "", {"type": "object"}),
    ToolSpec("records.get", "", {"type": "object", "properties": {"record_id": {}}}),
]


def lookup_playbook(**second_step) -> dict:
    return {
        **PLAYBOOK,
        "steps": [
            {
                "order": 1,
                "title": "Id",
                "instruction": "Enter the id.",
                "audience": ["staff"],
                "expects": "text",
                "lookup": {"tool": "records.get", "argument": "record_id"},
            },
            {
                "order": 2,
                "title": "State",
                "instruction": "Is {1.state} right?",
                "audience": ["staff"],
                "expects": "choice",
                "choices": ["open", "closed"],
                "answer_from": "1.state",
                **second_step,
            },
        ],
    }


def lookup_violations(pack_root: Path, playbook: dict, features=None) -> list[str]:
    manifest = {**MANIFEST, "features": features or [*MANIFEST["features"], GUIDED]}
    questions = [*QUESTIONS, {"id": "q3", "feature": "help"}]
    return violations(
        pack_root, RECORD_SPECS, manifest=manifest, playbook=playbook, questions=questions
    )


def test_a_lookup_playbook_loads_and_passes(pack_root: Path) -> None:
    assert lookup_violations(pack_root, lookup_playbook()) == []
    step = load_pack(pack_root).playbooks[0].steps[0]
    assert step.lookup.tool == "records.get" and step.lookup.argument == "record_id"


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (
            {"expects": "confirm", "choices": []},
            "playbook reset step 2: answer_from needs a choice step",
        ),
        (
            {"answer_from": "3.state"},
            "playbook reset step 2: answer_from '3.state' must name an earlier lookup step "
            "and a field, like 1.status",
        ),
        (
            {"instruction": "Is {4.state} right?"},
            "playbook reset step 2: {4.…} quotes a step that looks nothing up",
        ),
    ],
    ids=["answer on a non-choice", "answer from no lookup", "quote of no lookup"],
)
def test_answers_and_quotes_must_come_from_a_lookup(pack_root: Path, change, problem) -> None:
    assert problem in lookup_violations(pack_root, lookup_playbook(**change))


def test_a_lookup_needs_a_tool_of_a_playbook_feature(pack_root: Path) -> None:
    without_tool = [*MANIFEST["features"], {**GUIDED, "tools": []}]
    found = lookup_violations(pack_root, lookup_playbook(), features=without_tool)
    assert (
        "playbook reset step 1: lookup tool records.get is not a tool of a playbook feature"
    ) in found


def test_a_lookup_argument_must_be_one_the_tool_takes(pack_root: Path) -> None:
    playbook = lookup_playbook()
    playbook["steps"][0]["lookup"] = {"tool": "records.get", "argument": "id"}
    assert "playbook reset step 1: lookup tool records.get takes no id" in lookup_violations(
        pack_root, playbook
    )
