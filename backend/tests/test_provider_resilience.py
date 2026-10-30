import asyncio

from app.providers.base import AIProviderError
from app.providers.resilience import (
    classify_provider_failure,
    provider_is_cooling_down,
    provider_runtime_snapshot,
    record_provider_failure,
    record_provider_success,
    reset_provider_runtime_state,
)
from app.routers import ai as ai_router


def test_provider_failures_get_different_cooldowns_without_leaking_credentials():
    reset_provider_runtime_state()

    category, rate_limit_seconds = classify_provider_failure(
        AIProviderError("mistral", "HTTP 429 rate limit / quota exceeded")
    )
    assert category == "RATE_LIMIT"
    assert rate_limit_seconds >= 60

    category, auth_seconds = classify_provider_failure(
        AIProviderError("gemini", "401 invalid api key: abcdef123456789")
    )
    assert category == "AUTH_OR_PERMISSION"
    assert auth_seconds >= 300

    record_provider_failure(
        "mistral",
        AIProviderError("mistral", "HTTP 429 rate limit / quota exceeded"),
    )
    snapshot = provider_runtime_snapshot({"mistral": True, "gemini": False})
    states = {row["provider"]: row for row in snapshot}

    assert states["mistral"]["status"] == "COOLDOWN"
    assert states["mistral"]["last_failure"] == "RATE_LIMIT"
    assert states["mistral"]["retry_after_seconds"] > 0
    assert states["gemini"]["status"] == "NOT_CONFIGURED"
    assert "api_key" not in str(snapshot).lower()
    reset_provider_runtime_state()


def test_success_clears_provider_cooldown():
    reset_provider_runtime_state()
    record_provider_failure("mistral", AIProviderError("mistral", "429 quota exceeded"))
    assert provider_is_cooling_down("mistral") is True

    record_provider_success("mistral")
    assert provider_is_cooling_down("mistral") is False
    reset_provider_runtime_state()


def test_rate_limited_primary_is_skipped_and_free_fallback_is_used(monkeypatch):
    reset_provider_runtime_state()
    calls = {"mistral": 0, "openrouter": 0}

    class RateLimitedProvider:
        async def generate(self, prompt, system_instruction=None):
            calls["mistral"] += 1
            raise AIProviderError("mistral", "API error 429 rate limit quota exceeded")

    class WorkingProvider:
        async def generate(self, prompt, system_instruction=None):
            calls["openrouter"] += 1
            return "Fallback response from the working provider."

    monkeypatch.setattr(ai_router, "_eligible_fallbacks", lambda _primary: ["openrouter"])
    monkeypatch.setattr(
        ai_router,
        "get_provider",
        lambda name: RateLimitedProvider() if name == "mistral" else WorkingProvider(),
    )

    first = asyncio.run(ai_router.generate_reply_with_fallback("mistral", "prompt", timeout=3))
    second = asyncio.run(ai_router.generate_reply_with_fallback("mistral", "prompt", timeout=3))

    assert first == ("Fallback response from the working provider.", "openrouter")
    assert second == ("Fallback response from the working provider.", "openrouter")
    assert calls == {"mistral": 1, "openrouter": 2}
    assert provider_is_cooling_down("mistral") is True
    assert provider_is_cooling_down("openrouter") is False
    reset_provider_runtime_state()


def test_provider_status_endpoint_reports_only_safe_runtime_metadata(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.dependencies import get_current_user

    app = FastAPI()
    app.include_router(ai_router.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=99)
    monkeypatch.setattr(ai_router.settings, "mistral_api_key", "fake-secret-value")
    client = TestClient(app)
    response = client.get("/ai/providers")

    assert response.status_code == 200
    payload = response.json()
    assert any(row["provider"] == "mistral" and row["configured"] for row in payload["providers"])
    assert "fake-secret-value" not in response.text
    assert payload["fallback_policy"]["paid_fallbacks_enabled"] is False
