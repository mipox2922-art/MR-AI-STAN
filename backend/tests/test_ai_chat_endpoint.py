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


def test_fallback_chain_uses_one_total_timeout_budget(monkeypatch):
    import asyncio
    import time

    monkeypatch.setattr(ai_router, "_eligible_fallbacks", lambda _primary: ["fallback"])

    class SlowProvider:
        async def generate(self, prompt, system_instruction=None):
            await asyncio.sleep(0.5)
            return "too late"

    monkeypatch.setattr(ai_router, "get_provider", lambda _name: SlowProvider())
    started = time.monotonic()
    try:
        asyncio.run(ai_router.generate_reply_with_fallback("primary", "prompt", timeout=0.05))
    except AIProviderError:
        pass
    else:
        raise AssertionError("Slow provider should exceed the single shared timeout budget")

    assert time.monotonic() - started < 0.2


def test_chat_maps_provider_failure_to_gateway_error(tmp_path, monkeypatch):
    client, _ = build_chat_client(tmp_path)
    monkeypatch.setattr(ai_router, "get_provider", lambda _: FailingProvider())

    response = client.post(
        "/ai/chat",
        json={"message": "Tell me a short story", "provider": "openrouter"},
    )

    assert response.status_code == 502
    assert "AI provider returned empty or invalid response" in response.json()["detail"]
    assert "provider unavailable" in response.json()["detail"]
    assert "AIProviderError" not in response.json()["detail"]

    # Failed turns must survive reload instead of leaving only an old greeting in history.
    history = client.get("/ai/history").json()["messages"]
    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "Tell me a short story"
    assert "TEST AI PROVIDER" in history[1]["content"]


def test_prompt_repeats_verified_evidence_boundaries(tmp_path):
    _, session_factory = build_chat_client(tmp_path)
    with session_factory() as db:
        conversation = ai_router.get_or_create_conversation(
            db, user_id=1, title="Prompt boundary", session_id="prompt-boundary"
        )
        db.commit()
        prompt = ai_router.build_model_prompt(
            db, conversation.id, "summarize current work",
            {"available_task_list": [{"status": "WAITING_FOR_PROFILE"}]},
        )
    assert "WAITING_FOR_PROFILE means a profile/draft prerequisite is missing" in prompt
    assert "A provider health probe returning LIVE" in prompt


def test_job_search_chat_returns_results_without_calling_ai_provider(tmp_path, monkeypatch):
    client, _ = build_chat_client(tmp_path)

    async def fake_orchestration(_user_id, _text, _db):
        return {
            "status": "COMPLETED",
            "task_id": 42,
            "job_results": {
                "status": "COMPLETED",
                "query": "remote jobs",
                "count": 1,
                "results": [{
                    "title": "Remote Graphic Designer",
                    "company": "Example Studio",
                    "location": "Worldwide",
                    "url": "https://jobs.example.test/graphic-designer",
                    "source": "Remotive",
                }],
                "sources": ["Remotive"],
                "source_warnings": [],
            },
        }

    def provider_must_not_be_called(_name):
        raise AssertionError("Job search results must not depend on the AI provider")

    monkeypatch.setattr(ai_router, "run_orchestration", fake_orchestration)
    monkeypatch.setattr(ai_router, "get_provider", provider_must_not_be_called)

    response = client.post(
        "/ai/chat",
        json={"message": "TAFUTA KAZI SAWA FANYA", "provider": "openrouter"},
    )

    assert response.status_code == 200
    answer = response.json()["response"]
    assert "Remote Graphic Designer" in answer
    assert "Example Studio" in answer
    assert "https://jobs.example.test/graphic-designer" in answer
    assert "Hakuna maombi" in answer or "Hakuna maombi yaliyotumwa" in answer


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


def test_chat_session_store_is_bounded_per_user(tmp_path):
    client, session_factory = build_chat_client(tmp_path)
    with session_factory() as db:
        for index in range(55):
            conversation = ai_router.get_or_create_conversation(
                db, user_id=1, title=f"session {index}", session_id=f"browser-{index}"
            )
            db.commit()
        rows = db.query(ai_router.Conversation).filter(
            ai_router.Conversation.user_id == 1,
            ai_router.Conversation.session_id.is_not(None),
        ).order_by(ai_router.Conversation.id.desc()).all()
        assert len(rows) == 50
        assert rows[0].session_id == "browser-54"
        assert "browser-0" not in {row.session_id for row in rows}

def test_openrouter_extracts_text_from_content_block_arrays(monkeypatch):
    import asyncio
    from app.providers import openrouter as openrouter_module

    monkeypatch.setattr(openrouter_module.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(openrouter_module.settings, "openrouter_model", "openrouter/free")

    class FakeResponse:
        status_code = 200
        is_error = False

        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": [
                            {"type": "text", "text": "Karibu "},
                            {"type": "image", "image_url": "not-text"},
                            {"type": "text", "text": "Boss Ferisi"}
                        ]
                    },
                    "finish_reason": "stop"
                }]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    provider = openrouter_module.OpenRouterProvider()
    answer = asyncio.run(provider.generate("salamu", system_instruction="Jibu Kiswahili"))

    assert answer == "Karibu Boss Ferisi"

