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


class ChatRequest(BaseModel):
    message: str
    provider: str = "gemini"


class ChatResponse(BaseModel):
    response: str
    provider: str


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