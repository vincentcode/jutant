"""Request and response bodies. Their OpenAPI document is the source of the web client's types."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MAX_QUESTION_CHARS = 4000


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=500)


class Me(BaseModel):
    id: str  # staff number
    username: str
    role: str
    display_name: str
    attributes: dict[str, str] = {}  # e.g. the branch, shown in Settings


class HomeCardOut(BaseModel):
    title: str
    description: str
    feature_id: str
    icon: str = ""
    label: str = ""


class QuickActionOut(BaseModel):
    label: str
    feature_id: str


class HomeOut(BaseModel):
    """The home screen for the caller: only cards and actions for features their role may use."""

    cards: list[HomeCardOut] = []
    quick_actions: list[QuickActionOut] = []


class DocumentOut(BaseModel):
    id: UUID
    title: str
    doc_type: str
    effective_date: date | None = None
    indexed_at: datetime


class FeatureOut(BaseModel):
    id: str
    template: str
    title: str
    description: str
    group: str = ""  # for the client's menu: "Look something up", "Policies and documents"...
    examples: list[str] = []  # questions to offer on the first screen (the pack's suggestions)


class AppOut(BaseModel):
    """What the client shows before and around everything else: the assistant's name (the
    pack's) and the deployment's accent colour."""

    name: str
    accent: str | None = None


class ConversationOut(BaseModel):
    id: UUID
    title: str
    updated_at: datetime


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class CitationOut(BaseModel):
    kind: Literal["document", "record"]
    title: str
    locator: str


class StepOut(BaseModel):
    """A playbook step a turn showed: the client shows the latest as a card, earlier ones as
    a line each."""

    playbook_id: str
    playbook_title: str = ""
    order: int
    title: str
    instruction: str
    expects: Literal["confirm", "choice", "text", "none"]
    choices: list[str] = []
    answered: str | None = None  # answered from a looked-up record


FeedbackReason = Literal["wrong_answer", "wrong_source", "wrong_feature", "too_slow", "other"]


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    reason: FeedbackReason | None = None  # for a thumbs-down
    comment: str = Field("", max_length=1000)


class FeedbackOut(BaseModel):
    rating: Literal["up", "down"]
    reason: FeedbackReason | None = None
    comment: str = ""


class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    feature_id: str | None = None
    citations: list[CitationOut] = []
    steps: list[StepOut] = []
    feedback: FeedbackOut | None = None  # the reader's own rating of an answer
    created_at: datetime


class AskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    feature_id: str | None = None
    upload_id: UUID | None = None


class UploadOut(BaseModel):
    upload_id: UUID
    filename: str
    characters: int
    note: str = ""  # how it was read, when staff should know: "2 of 3 pages read by OCR"


class HealthOut(BaseModel):
    database: bool
    model: bool
    mcp_servers: dict[str, bool]
