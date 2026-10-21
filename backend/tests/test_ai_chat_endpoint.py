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
    assert "AI provider returned empty or invalid response" in response.json()["detail"]
    assert "AIProviderError" in response.json()["detail"]


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


def test_chat_history_isolated_by_session_and_context_keeps_prior_turns(tmp_path, monkeypatch):
    client, session_factory = build_chat_client(tmp_path)

    class CapturingProvider:
        def __init__(self):
            self.prompts = []

        async def generate(self, prompt, system_instruction=None):
            self.prompts.append(prompt)
            return f"reply-{len(self.prompts)}"

    provider = CapturingProvider()
    monkeypatch.setattr(ai_router, "get_provider", lambda _: provider)

    async def no_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(ai_router.manager, "broadcast", no_broadcast)

    first = client.post("/ai/chat", json={
        "message": "Tell me a short story",
        "provider": "openrouter",
        "session_id": "browser-session-a",
    })
    second = client.post("/ai/chat", json={
        "message": "Continue that story",
        "provider": "openrouter",
        "session_id": "browser-session-a",
    })
    third = client.post("/ai/chat", json={
        "message": "Tell me a short story",
        "provider": "openrouter",
        "session_id": "browser-session-b",
    })

    assert first.status_code == second.status_code == third.status_code == 200
    assert "BOSS: Tell me a short story" in provider.prompts[1]
    assert "MR AI: reply-1" in provider.prompts[1]
    assert "Continue that story" in provider.prompts[1]
    assert "MR AI: reply-1" not in provider.prompts[2]
    assert "browser-session-a" not in provider.prompts[2]

    history_a = client.get("/ai/history?session_id=browser-session-a").json()
    history_b = client.get("/ai/history?session_id=browser-session-b").json()
    assert len(history_a["messages"]) == 4
    assert len(history_b["messages"]) == 2
    assert history_a["session_id"] == "browser-session-a"
    assert history_b["session_id"] == "browser-session-b"
    with session_factory() as db:
        assert db.query(ai_router.Conversation).filter_by(user_id=1).count() == 2


def test_ai_health_returns_live_after_a_real_provider_call(tmp_path, monkeypatch):
    client, _ = build_chat_client(tmp_path)

    class HealthProvider:
        async def generate(self, prompt, system_instruction=None):
            assert prompt == "Reply with exactly the word LIVE."
            assert system_instruction
            return "LIVE"

    monkeypatch.setattr(ai_router, "get_provider", lambda _: HealthProvider())

    async def no_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(ai_router.manager, "broadcast", no_broadcast)
    response = client.get("/ai/health?provider=gemini")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "LIVE"
    assert payload["provider"] == "gemini"
    assert isinstance(payload["latency_ms"], int)
    assert "api_key" not in payload
    assert "token" not in payload


def test_ai_health_reports_safe_provider_failure_without_credentials(tmp_path, monkeypatch):
    client, _ = build_chat_client(tmp_path)

    class FailingHealthProvider:
        async def generate(self, prompt, system_instruction=None):
            raise AIProviderError("test-provider", "request rejected: Bearer abcdef123456789")

    monkeypatch.setattr(ai_router, "get_provider", lambda _: FailingHealthProvider())
    response = client.get("/ai/health?provider=gemini")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ERROR"
    assert payload["reason"]
    assert "abcdef123456789" not in payload["reason"]


def test_ai_runtime_state_times_out_active_state_after_30_seconds(tmp_path, monkeypatch):
    from app.models import AIStateSnapshot
    from datetime import datetime, timedelta

    client, session_factory = build_chat_client(tmp_path)
    with session_factory() as db:
        db.add(AIStateSnapshot(
            user_id=1,
            state="THINKING",
            reason_safe="in progress",
            request_id="old-request",
            updated_at=datetime.utcnow() - timedelta(seconds=45),
        ))
        db.commit()

    async def no_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(ai_router.manager, "broadcast", no_broadcast)
    response = client.get("/ai/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "ERROR"
    assert "timed out" in payload["reason"]
