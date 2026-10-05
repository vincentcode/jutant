"""Request and response bodies. Their OpenAPI document is the source of the web client's types."""

from datetime import datetime
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


class FeatureOut(BaseModel):
    id: str
    template: str
    title: str
    description: str


class ConversationOut(BaseModel):
    id: UUID
    title: str
    updated_at: datetime


class CitationOut(BaseModel):
    kind: Literal["document", "record"]
    title: str
    locator: str


class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    feature_id: str | None = None
    citations: list[CitationOut] = []
    created_at: datetime


class AskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    feature_id: str | None = None
    upload_id: UUID | None = None


class UploadOut(BaseModel):
    upload_id: UUID
    filename: str
    characters: int


class HealthOut(BaseModel):
    database: bool
    model: bool
    mcp_servers: dict[str, bool]
