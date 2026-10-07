from app.config import settings
from app.routers.system import _service_status


def test_service_status_reports_unconfigured_ai_truthfully(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "kimi_api_key", "")

    services = _service_status()

    assert services["ai_core"] == "NOT_CONFIGURED"
    assert services["gemini"] == "NOT_CONFIGURED"
    assert services["kimi"] == "NOT_CONFIGURED"


def test_service_status_reports_configured_provider_without_claiming_online(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "configured-for-test")
    monkeypatch.setattr(settings, "kimi_api_key", "")

    services = _service_status()

    assert services["ai_core"] == "READY"
    assert services["gemini"] == "CONFIGURED"
    assert services["kimi"] == "NOT_CONFIGURED"
