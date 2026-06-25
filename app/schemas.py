"""Pydantic request/response models."""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Pragmatic email shape check (no external validator dep — real verification is
# the planned OTP flow). Stored lowercased.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---- Auth ----
class UserCreate(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address.")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    is_admin: bool
    created_at: datetime


# ---- Projects ----
class ProjectCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class ScriptGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class ScriptUpdate(BaseModel):
    generated_script: str = Field(min_length=1, max_length=8000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prompt: str
    generated_script: str | None
    video_path: str | None
    background: str | None
    music: str | None
    status: str
    error: str | None
    timestamp: datetime


class ScriptResponse(BaseModel):
    project_id: int
    generated_script: str
