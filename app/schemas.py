"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- Auth ----
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
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
    status: str
    error: str | None
    timestamp: datetime


class ScriptResponse(BaseModel):
    project_id: int
    generated_script: str
