from app.config import settings
from app.routers.system import _service_status


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
    assert services["web_search"] == "NOT_CONFIGURED"
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
