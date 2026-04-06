import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: str
    username: str
    password: str
    display_name: str | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    display_name: str | None = None
    is_rater: bool
    rater_level: str
    total_ratings: int
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str
