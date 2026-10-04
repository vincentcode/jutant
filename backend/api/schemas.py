"""Pydantic request and response models. Their OpenAPI is the source for the client's types."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class Me(BaseModel):
    id: str
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
    kind: str
    title: str
    locator: str


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    feature_id: str | None = None
    citations: list[CitationOut] = []
    created_at: datetime


class AskRequest(BaseModel):
    text: str
    feature_id: str | None = None
    upload_id: str | None = None


class UploadOut(BaseModel):
    upload_id: str


class HealthOut(BaseModel):
    database: bool
    model: bool
    mcp_servers: dict[str, bool]
