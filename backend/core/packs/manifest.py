"""The shape of a pack's `pack.yaml`. A manifest that does not match fails to load."""

from typing import Any, Literal

from pydantic import BaseModel, model_validator

TemplateId = Literal[
    "document_qa",
    "record_lookup",
    "record_summary",
    "guided_playbook",
    "document_extraction",
    "checklist",
]


class McpServerRef(BaseModel):
    platform: str | None = None  # e.g. "documents"
    pack: str | None = None  # e.g. "transactions"
    url: str | None = None  # overrides the default address


class RouteDef(BaseModel):
    patterns: list[str] = []  # regular expressions; a match routes here without the model
    examples: list[str] = []  # example questions, for routing by meaning


class ArgumentDef(BaseModel):
    """One argument of a prefetched call: `{question: true}`, `{match: '<regex>'}` or
    `{value: ...}`."""

    question: bool = False
    match: str | None = None
    value: Any = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "ArgumentDef":
        if sum((self.question, self.match is not None, self.value is not None)) != 1:
            raise ValueError("set exactly one of question, match or value")
        return self


class PrefetchDef(BaseModel):
    tool: str
    arguments: dict[str, ArgumentDef]


class FeatureDef(BaseModel):
    id: str
    template: TemplateId
    title: str
    description: str
    prompt: str  # path relative to the pack
    tools: list[str] = []
    roles: list[str] = []  # empty = all roles
    route: RouteDef = RouteDef()
    prefetch: list[PrefetchDef] = []
    # Questions the client offers on its first screen. Unlike route examples, these are asked
    # for real, so they must be ones the deployment can answer.
    suggestions: list[str] = []


class Classification(BaseModel):
    label: str
    roles: list[str] | Literal["all"]


class FieldRuleDef(BaseModel):
    tool: str
    hide: list[str]
    unless_role: list[str] = []


class ExtractionSchema(BaseModel):
    type: str
    fields: list[str]


class HomeCard(BaseModel):
    """A starting point on the client's home screen: it starts the feature it names."""

    title: str  # "Investigate a transaction"
    description: str  # "Search payments, transfers and transaction errors."
    feature: str
    icon: str = ""  # a Lucide icon name, e.g. "landmark"; the client has a default
    label: str = ""  # a short tag under it, e.g. "Payments"


class QuickAction(BaseModel):
    """A chip in the client's question box that picks a feature."""

    label: str  # "Transaction"
    feature: str


class HomeDef(BaseModel):
    cards: list[HomeCard] = []
    quick_actions: list[QuickAction] = []


class PackManifest(BaseModel):
    name: str
    display_name: str
    roles: list[str]
    audiences: list[str]
    caller_attributes: list[str] = []
    default_feature: str
    mcp_servers: list[McpServerRef]
    features: list[FeatureDef]
    classifications: list[Classification]
    field_rules: list[FieldRuleDef] = []
    extraction_schemas: list[ExtractionSchema] = []
    # What each tool looks at, in staff's words, for the client's activity line:
    # "Checking the account's transactions…", "Not allowed: the account's transactions".
    tool_labels: dict[str, str] = {}
    home: HomeDef = HomeDef()  # the client's home screen
    policy: str  # dotted path to a module exposing RULES
