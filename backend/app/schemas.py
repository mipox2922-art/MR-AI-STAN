from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthStatusResponse(BaseModel):
    setup_required: bool


class ChatRequest(BaseModel):
    message: str
    provider: str = "gemini"
    tool_context: dict | None = None


class ChatResponse(BaseModel):
    response: str
    provider: str
    request_id: str | None = None
    elapsed_ms: int | None = None


class MemoryCreate(BaseModel):
    key: str
    value: str


class MemoryUpdate(BaseModel):
    value: str


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: str = "NORMAL"
    deadline: datetime | None = None
    agent: str | None = None


class TaskUpdate(BaseModel):
    # Generic user-facing edits cannot forge completion or overwrite execution evidence.
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=12000)
    status: Literal[
        "PENDING",
        "RUNNING",
        "IN_PROGRESS",
        "WAITING",
        "WAITING_FOR_HAND",
        "WAITING_APPROVAL",
    ] | None = None
    priority: Literal["LOW", "NORMAL", "HIGH", "CRITICAL"] | None = None
    progress: int | None = Field(default=None, ge=0, le=99)


class ScheduleCreate(BaseModel):
    title: str
    command: str
    run_at: datetime
    interval_minutes: int | None = None


class ScheduleUpdate(BaseModel):
    title: str | None = None
    command: str | None = None
    run_at: datetime | None = None
    interval_minutes: int | None = None
    status: str | None = None
