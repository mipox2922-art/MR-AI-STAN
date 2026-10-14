from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.providers.base import AIProviderError
from app.routers import ai as ai_router


def build_chat_client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'chat.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(ai_router.router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    client = TestClient(app)
    return client, session_factory


class SuccessfulProvider:
    async def generate(self, prompt, system_instruction=None):
        assert "CURRENT USER MESSAGE:" in prompt
        assert system_instruction
        return "MR AI test reply"


class FailingProvider:
    async def generate(self, prompt, system_instruction=None):
        raise AIProviderError("test-provider", "provider unavailable")


def test_chat_returns_reply_and_persists_conversation_history(tmp_path, monkeypatch):
    client, session_factory = build_chat_client(tmp_path)
    monkeypatch.setattr(ai_router, "get_provider", lambda _: SuccessfulProvider())

    async def no_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(ai_router.manager, "broadcast", no_broadcast)

    response = client.post(
        "/ai/chat",
        json={"message": "Tell me a short story", "provider": "openrouter"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "MR AI test reply"
    assert payload["provider"] == "openrouter"
    assert payload["request_id"]
    assert payload["elapsed_ms"] >= 0

    history_response = client.get("/ai/history")
    assert history_response.status_code == 200
    messages = history_response.json()["messages"]
    assert [(item["role"], item["content"]) for item in messages] == [
        ("user", "Tell me a short story"),
        ("assistant", "MR AI test reply"),
    ]

    with session_factory() as db:
        assert db.query(ai_router.Message).count() == 2
        assert db.query(ai_router.ActivityLog).filter_by(action="AI_CHAT").count() == 1


def test_chat_rejects_empty_and_oversized_messages(tmp_path, monkeypatch):
    client, _ = build_chat_client(tmp_path)

    def provider_must_not_be_called(_name):
        raise AssertionError("Provider must not be called for invalid input")

    monkeypatch.setattr(ai_router, "get_provider", provider_must_not_be_called)

    empty = client.post("/ai/chat", json={"message": "   "})
    assert empty.status_code == 400
    assert empty.json()["detail"] == "Message cannot be empty"

    oversized = client.post("/ai/chat", json={"message": "x" * 6001})
    assert oversized.status_code == 413
    assert "6000" in oversized.json()["detail"]


def test_chat_maps_provider_failure_to_gateway_error(tmp_path, monkeypatch):
    client, _ = build_chat_client(tmp_path)
    monkeypatch.setattr(ai_router, "get_provider", lambda _: FailingProvider())

    response = client.post(
        "/ai/chat",
        json={"message": "Tell me a short story", "provider": "openrouter"},
    )

    assert response.status_code == 502
    assert "provider unavailable" in response.json()["detail"]


def test_chat_rejects_unknown_provider(tmp_path, monkeypatch):
    client, _ = build_chat_client(tmp_path)

    def unknown_provider(_name):
        raise ValueError("Unknown AI provider: alien")

    monkeypatch.setattr(ai_router, "get_provider", unknown_provider)

    response = client.post(
        "/ai/chat",
        json={"message": "Tell me a short story", "provider": "alien"},
    )

    assert response.status_code == 400
    assert "Unknown provider" in response.json()["detail"]
