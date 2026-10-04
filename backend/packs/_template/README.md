# Pack template

Copy this folder to `packs/<name>/` and fill in each part:

1. `pack.yaml`: roles, caller attributes, classifications, features, extraction schemas.
2. `prompts/`: `system.md` and one file per feature.
3. `playbooks/`: one YAML file per procedure; every step has an audience.
4. `policy/rules.py`: a rule for every tool.
5. `adapters/`: client protocols, real clients and fakes for the area's systems.
6. `mcp_servers/`: one server per system group, every tool under `@guarded_tool`.
7. `extraction/schemas.yaml`: the document types staff upload and their fields.
8. `evals/questions.yaml`: at least one question per feature.

No change to `core/`, `apps/`, `providers/` or `mcp_servers/common` should be needed.
