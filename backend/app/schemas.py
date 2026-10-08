from datetime import datetime
from pydantic import BaseModel


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
    status: str | None = None
    priority: str | None = None
    progress: int | None = None
    result: str | None = None
    error: str | None = None


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
