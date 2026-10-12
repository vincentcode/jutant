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
    "conversation",
]


class McpServerRef(BaseModel):
    platform: str | None = None  # e.g. "documents"
    pack: str | None = None  # e.g. "transactions"
    url: str | None = None  # overrides the default address


class RouteDef(BaseModel):
    patterns: list[str] = []  # regular expressions; a match routes here without the model
    examples: list[str] = []  # example questions, for routing by meaning


class ArgumentDef(BaseModel):
    """One argument of a prefetched call: `{question: true}`, `{match: '<regex>'}`,
    `{value: ...}`, `{entity: <type>}`, `{choose: {...}}` or `{detail: <name>}`; with
    `optional: true`, left out when it has no value."""

    question: bool = False
    match: str | None = None
    value: Any = None
    entity: str | None = None  # an entity type the pack declares: the conversation's current one
    # value -> what it means: the model picks the one the question is about, or none
    choose: dict[str, str] = {}
    detail: str | None = None  # one of the feature's details, once staff gave it
    optional: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> "ArgumentDef":
        given = (
            self.question,
            self.match is not None,
            self.value is not None,
            self.entity,
            self.choose,
            self.detail,
        )
        if sum(bool(g) for g in given) != 1:
            raise ValueError("set exactly one of question, match, value, entity, choose or detail")
        return self


class DetailDef(BaseModel):
    """Something a feature must know before it looks anything up: an entity's id, one of the
    values listed in `choose` (value: title), or a date."""

    label: str  # "the customer's phone number": used to ask for it
    entity: str | None = None
    choose: dict[str, str] = {}
    words: dict[str, list[str]] = {}  # value -> other words that name it in a message
    date: bool = False
    ask: str = ""  # the question asking for it alone
    title: str = ""  # its name on a button: "Phone number"

    @model_validator(mode="after")
    def _exactly_one(self) -> "DetailDef":
        if sum(bool(g) for g in (self.entity, self.choose, self.date)) != 1:
            raise ValueError("set exactly one of entity, choose or date")
        if unknown := sorted(set(self.words) - set(self.choose)):
            raise ValueError(f"words name values not in choose: {', '.join(unknown)}")
        return self


class NeedsDef(BaseModel):
    """Which details a feature needs: `first`, asked one at a time; then any one complete set of
    `one_of`, or with `by` (a detail asked first), of `one_of_by` for its value."""

    first: list[str] = []
    one_of: list[list[str]] = []
    by: str | None = None
    one_of_by: dict[str, list[list[str]]] = {}


class EntityDef(BaseModel):
    """A kind of thing staff talk about: how to recognise its id, and what staff call it."""

    pattern: str
    words: list[str] = []
    name_field: str | None = None  # in tool results, the field holding one's name


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
    # What to ask for when a question gives none of what the prefetch calls need.
    ask_for: str = ""
    # Where follow-ups to this feature's answers go, if not to itself.
    follow_ups: str = ""
    # What it must know before looking anything up, by name; asked for in code when missing.
    details: dict[str, DetailDef] = {}
    needs: NeedsDef | None = None


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


class HomeDef(BaseModel):
    cards: list[HomeCard] = []


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
    # What staff talk about, by type: the conversation keeps the current one of each, so a
    # follow-up's lookups use it ("why did it fail?" after TX-0002).
    entities: dict[str, EntityDef] = {}
    policy: str  # dotted path to a module exposing RULES
