"""Checks every pack must pass before the platform will run it.

`check` returns a list of plain-language violations; an empty list means the pack passes.

- every tool named in a feature exists on one of the pack's MCP servers;
- every tool the pack's servers expose has an access rule;
- every role named by a feature, classification or field rule is one of the pack's roles;
- every playbook step has at least one audience, and each is one of the pack's audiences;
- every `next_on` target is an existing step, and every choice step lists its choices;
- no branch of a choice runs on, in step order, into another branch of the same choice;
- `default_feature` exists;
- every prompt file exists and is not empty;
- every `document_extraction` feature has at least one extraction schema;
- every route pattern is a valid regular expression;
- every prefetched call uses one of its feature's tools, with arguments the tool accepts, and
  each `match` is a valid regular expression with at most one group;
- every feature has at least one eval question.
"""

import re

from core.packs.loader import SYSTEM_PROMPT, Pack
from core.packs.manifest import PrefetchDef
from core.types import Playbook, ToolSpec


def check(pack: Pack, tool_specs: list[ToolSpec]) -> list[str]:
    m = pack.manifest
    problems: list[str] = []
    roles = set(m.roles)
    audiences = set(m.audiences)
    servers = {ref.platform or ref.pack for ref in m.mcp_servers}
    tools = {s.name for s in tool_specs if s.name.split(".", 1)[0] in servers}
    ruled = {r.tool for r in pack.rules}
    feature_ids = {f.id for f in m.features}
    specs = {s.name: s for s in tool_specs}

    for f in m.features:
        for tool in f.tools:
            if tool not in tools:
                problems.append(f"feature {f.id}: tool {tool} is not offered by any pack server")
        for role in sorted(set(f.roles) - roles):
            problems.append(f"feature {f.id}: unknown role {role}")
        if not _non_empty(pack, f.prompt):
            problems.append(f"feature {f.id}: prompt file {f.prompt} is missing or empty")
        if f.template == "document_extraction" and not m.extraction_schemas:
            problems.append(f"feature {f.id}: document_extraction needs an extraction schema")
        for pattern in f.route.patterns:
            if (error := _regex_problem(pattern)) is not None:
                problems.append(f"feature {f.id}: route pattern {pattern!r}: {error}")
        for p in f.prefetch:
            problems.extend(_prefetch_problems(f.id, f.tools, p, specs))

    for tool in sorted(tools - ruled):
        problems.append(f"tool {tool} has no access rule")

    for c in m.classifications:
        if c.roles != "all":
            for role in sorted(set(c.roles) - roles):
                problems.append(f"classification {c.label}: unknown role {role}")
    for r in m.field_rules:
        for role in sorted(set(r.unless_role) - roles):
            problems.append(f"field rule on {r.tool}: unknown role {role}")

    for playbook in pack.playbooks:
        orders = {s.order for s in playbook.steps}
        for step in playbook.steps:
            where = f"playbook {playbook.id} step {step.order}"
            if not step.audience:
                problems.append(f"{where}: has no audience")
            for audience in sorted(set(step.audience) - audiences):
                problems.append(f"{where}: unknown audience {audience}")
            for answer, target in step.next_on.items():
                if target not in orders:
                    problems.append(f"{where}: next_on {answer} points to missing step {target}")
            if step.expects == "choice" and not step.choices:
                problems.append(f"{where}: a choice step needs choices")
        problems.extend(_branches_running_into_each_other(playbook))

    if m.default_feature not in feature_ids:
        problems.append(f"default_feature {m.default_feature} is not a feature")
    if not _non_empty(pack, SYSTEM_PROMPT):
        problems.append(f"{SYSTEM_PROMPT} is missing or empty")

    asked = {q.get("feature") for q in pack.eval_questions}
    for feature_id in sorted(feature_ids - asked):
        problems.append(f"feature {feature_id} has no eval question")
    return problems


def _branches_running_into_each_other(playbook: Playbook) -> list[str]:
    """A branch of a choice that, with no `next_on` of its own, carries on in step order into
    another branch of the same choice: the failed-transfer branch running on into the advice
    for pending transfers."""
    steps = sorted(playbook.steps, key=lambda s: s.order)
    problems = []
    for choice in steps:
        if choice.expects != "choice":
            continue
        branches = {target: answer for answer, target in choice.next_on.items()}
        for target, answer in branches.items():
            current = next((s for s in steps if s.order == target), None)
            while current is not None and not current.next_on:
                following = next((s for s in steps if s.order > current.order), None)
                if (
                    following is not None
                    and following.order in branches
                    and following.order != target
                ):
                    problems.append(
                        f"playbook {playbook.id} step {current.order}: the {answer!r} branch of "
                        f"step {choice.order} runs on into step {following.order}, the "
                        f"{branches[following.order]!r} branch; end it with next_on"
                    )
                    break
                current = following
    return problems


def _regex_problem(pattern: str, max_groups: int | None = None) -> str | None:
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return f"not a valid regular expression ({exc})"
    if max_groups is not None and compiled.groups > max_groups:
        return f"has {compiled.groups} groups; use at most {max_groups}"
    return None


def _prefetch_problems(
    feature_id: str, feature_tools: list[str], p: PrefetchDef, specs: dict[str, ToolSpec]
) -> list[str]:
    where = f"feature {feature_id}: prefetch {p.tool}"
    if p.tool not in feature_tools:
        return [f"{where}: the feature's tools do not include it"]
    problems = []
    accepted = set(specs[p.tool].input_schema.get("properties", {})) if p.tool in specs else None
    for name, argument in p.arguments.items():
        if accepted is not None and name not in accepted:
            problems.append(f"{where}: the tool takes no argument {name}")
        if argument.match is not None and (error := _regex_problem(argument.match, 1)):
            problems.append(f"{where}: argument {name}: {error}")
    return problems


def _non_empty(pack: Pack, relative: str) -> bool:
    path = pack.path / relative
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
