"""Checks every pack must pass before the platform will run it.

`check` returns a list of plain-language violations; an empty list means the pack passes.

- every tool named in a feature exists on one of the pack's MCP servers;
- every tool the pack's servers expose has an access rule;
- every role named by a feature, classification or field rule is one of the pack's roles;
- every playbook step has at least one audience, and each is one of the pack's audiences;
- every `next_on` target is an existing step, and every choice step lists its choices;
- `default_feature` exists;
- every prompt file exists and is not empty;
- every `document_extraction` feature has at least one extraction schema;
- every feature has at least one eval question.
"""

from core.packs.loader import SYSTEM_PROMPT, Pack
from core.types import ToolSpec


def check(pack: Pack, tool_specs: list[ToolSpec]) -> list[str]:
    m = pack.manifest
    problems: list[str] = []
    roles = set(m.roles)
    audiences = set(m.audiences)
    servers = {ref.platform or ref.pack for ref in m.mcp_servers}
    tools = {s.name for s in tool_specs if s.name.split(".", 1)[0] in servers}
    ruled = {r.tool for r in pack.rules}
    feature_ids = {f.id for f in m.features}

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

    if m.default_feature not in feature_ids:
        problems.append(f"default_feature {m.default_feature} is not a feature")
    if not _non_empty(pack, SYSTEM_PROMPT):
        problems.append(f"{SYSTEM_PROMPT} is missing or empty")

    asked = {q.get("feature") for q in pack.eval_questions}
    for feature_id in sorted(feature_ids - asked):
        problems.append(f"feature {feature_id} has no eval question")
    return problems


def _non_empty(pack: Pack, relative: str) -> bool:
    path = pack.path / relative
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
