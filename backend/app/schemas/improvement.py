"""Pydantic schemas for ImprovementFeedback."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TargetType = Literal[
    "story", "story_title", "story_image", "story_summary",
    "article", "source", "source_dimension", "layout", "homepage", "other",
]

IssueType = Literal[
    "wrong_title", "bad_image", "wrong_clustering", "bad_summary",
    "wrong_source_class", "layout_issue", "bug", "feature_request", "other",
]

Status = Literal["open", "in_progress", "done", "wont_do", "duplicate"]
Priority = Literal["low", "medium", "high"]


class ImprovementSubmit(BaseModel):
    target_type: TargetType
    target_id: str | None = Field(None, max_length=100)
    target_url: str | None = Field(None, max_length=500)
    issue_type: IssueType
    current_value: str | None = Field(None, max_length=5000)
    suggested_value: str | None = Field(None, max_length=5000)
    reason: str | None = Field(None, max_length=2000)
    rater_name: str | None = Field(None, max_length=100)
    rater_contact: str | None = Field(None, max_length=200)
    priority: Priority | None = None


class ImprovementResponse(BaseModel):
    id: uuid.UUID
    status: str
    message: str
    similar_count: int = 0  # How many others flagged the same target+issue


class ImprovementDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_type: str
    target_id: str | None
    target_url: str | None
    issue_type: str
    current_value: str | None
    suggested_value: str | None
    reason: str | None
    rater_name: str | None
    rater_contact: str | None
    status: str
    priority: str | None
    admin_notes: str | None
    resolved_at: datetime | None
    created_at: datetime


class ImprovementUpdate(BaseModel):
    status: Status | None = None
    priority: Priority | None = None
    admin_notes: str | None = None


class ImprovementListResponse(BaseModel):
    items: list[ImprovementDetail]
    total: int
    open: int
    in_progress: int
