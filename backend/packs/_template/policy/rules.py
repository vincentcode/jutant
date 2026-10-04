from core.policy.rules import ALLOW, FunctionRule, Rule

RULES: list[Rule] = [
    FunctionRule("documents.search", lambda caller, arguments, record: ALLOW),
]
