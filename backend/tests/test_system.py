from app.config import settings
from app.routers.system import _default_ai_provider, _service_status


def test_service_status_reports_unconfigured_ai_truthfully(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "kimi_api_key", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "mistral_api_key", "")
    monkeypatch.setattr(settings, "xai_api_key", "")

    services = _service_status()

    assert services["ai_core"] == "NOT_CONFIGURED"
    assert services["gemini"] == "NOT_CONFIGURED"
    assert services["kimi"] == "NOT_CONFIGURED"
    assert services["openrouter"] == "NOT_CONFIGURED"
    assert services["mistral"] == "NOT_CONFIGURED"
    assert services["grok"] == "NOT_CONFIGURED"
    assert services["web_search"] == "AVAILABLE"
    assert services["security"] == "NOT_CONFIGURED"


def test_service_status_reports_configured_provider_without_claiming_online(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "configured-for-test")
    monkeypatch.setattr(settings, "kimi_api_key", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    services = _service_status()

    assert services["ai_core"] == "CONFIGURED"
    assert services["gemini"] == "CONFIGURED"
    assert services["kimi"] == "NOT_CONFIGURED"
    assert services["openrouter"] == "NOT_CONFIGURED"


def test_openrouter_key_marks_core_ready_and_reports_openrouter(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "kimi_api_key", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "configured-for-test")
    monkeypatch.setattr(settings, "openrouter_model", "openrouter/free")
    monkeypatch.setattr(settings, "mistral_api_key", "")
    monkeypatch.setattr(settings, "xai_api_key", "")

    services = _service_status()
    assert services["ai_core"] == "CONFIGURED"
    assert services["openrouter"] == "CONFIGURED"


def test_mistral_and_grok_keys_are_reported_as_configured(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "kimi_api_key", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "mistral_api_key", "test-mistral-key")
    monkeypatch.setattr(settings, "xai_api_key", "test-xai-key")

    services = _service_status()
    assert services["ai_core"] == "CONFIGURED"
    assert services["mistral"] == "CONFIGURED"
    assert services["grok"] == "CONFIGURED"


def test_database_status_reports_current_connection():
    from app.routers.system import _database_status

    assert _database_status() == "ONLINE"

def _set_ai_provider_settings(monkeypatch, **overrides):
    defaults = {
        "openrouter_api_key": "",
        "openrouter_model": "openrouter/free",
        "gemini_api_key": "",
        "gemini_model": "gemini-3.8-flash",
        "gemini_tier": "FREE",
        "mistral_api_key": "",
        "mistral_model": "mistral-small-latest",
        "xai_api_key": "",
        "grok_model": "grok-4.7",
        "kimi_api_key": "",
        "kimi_model": "kimi-k2",
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(settings, name, value)


def test_free_gemini_is_preferred_over_mistral_and_grok(monkeypatch):
    _set_ai_provider_settings(
        monkeypatch,
        gemini_api_key="configured-gemini-key",
        mistral_api_key="configured-mistral-key",
        xai_api_key="configured-xai-key",
    )

    assert _default_ai_provider() == ("gemini", "gemini-3.8-flash", "FREE")


def test_free_openrouter_route_is_preferred_over_gemini(monkeypatch):
    _set_ai_provider_settings(
        monkeypatch,
        openrouter_api_key="configured-openrouter-key",
        gemini_api_key="configured-gemini-key",
    )

    assert _default_ai_provider() == ("openrouter", "openrouter/free", "OPENROUTER_FREE")


def test_free_gemini_is_preferred_over_paid_openrouter_model(monkeypatch):
    _set_ai_provider_settings(
        monkeypatch,
        openrouter_api_key="configured-openrouter-key",
        openrouter_model="provider/paid-model",
        gemini_api_key="configured-gemini-key",
    )

    assert _default_ai_provider() == ("gemini", "gemini-3.8-flash", "FREE")


def test_paid_provider_is_not_selected_for_unattended_default_when_no_free_route_exists(monkeypatch):
    _set_ai_provider_settings(
        monkeypatch,
        openrouter_api_key="",
        gemini_api_key="configured-gemini-key",
        gemini_tier="PAID",
        mistral_api_key="configured-mistral-key",
        xai_api_key="configured-xai-key",
    )

    assert _default_ai_provider() == (None, None, None)


def test_system_status_requires_authentication_without_bearer_token():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import system as system_router

    app = FastAPI()
    app.include_router(system_router.router)

    response = TestClient(app).get("/system/status")

    assert response.status_code in {401, 403}

