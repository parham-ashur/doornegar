"""Pydantic schemas for SourceSuggestion."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SuggestionType = Literal[
    "media", "telegram", "x_twitter", "youtube", "instagram", "website", "other"
]

SuggestedCategory = Literal[
    "state", "semi_state", "independent", "diaspora", "not_sure"
]

SuggestionStatus = Literal[
    "pending", "approved", "rejected", "duplicate", "already_tracked"
]


class SuggestionSubmit(BaseModel):
    """What a public visitor submits via the form."""
    suggestion_type: SuggestionType
    name: str = Field(..., min_length=2, max_length=200)
    url: str = Field(..., min_length=3, max_length=500)
    language: str | None = Field(None, max_length=10)
    suggested_category: SuggestedCategory | None = None
    description: str | None = Field(None, max_length=2000)
    submitter_name: str | None = Field(None, max_length=100)
    submitter_contact: str | None = Field(None, max_length=200)
    submitter_notes: str | None = Field(None, max_length=2000)


class SuggestionResponse(BaseModel):
    """Public response after submission — confirms receipt."""
    id: uuid.UUID
    status: SuggestionStatus
    message: str


class SuggestionDetail(BaseModel):
    """Full suggestion record — admin only."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    suggestion_type: str
    name: str
    url: str
    language: str | None
    suggested_category: str | None
    description: str | None
    submitter_name: str | None
    submitter_contact: str | None
    submitter_notes: str | None
    status: str
    reviewer_notes: str | None
    reviewed_at: datetime | None
    created_at: datetime


class SuggestionUpdate(BaseModel):
    """Admin-only update — change status or add reviewer notes."""
    status: SuggestionStatus | None = None
    reviewer_notes: str | None = None


class SuggestionListResponse(BaseModel):
    suggestions: list[SuggestionDetail]
    total: int
    pending: int
