import pytest

from app.config import settings
from app.providers.factory import _build
from app.providers.openrouter import OpenRouterProvider


def test_openrouter_provider_requires_server_side_key(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider()


def test_factory_builds_openrouter_provider_when_selected(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key-not-real")
    monkeypatch.setattr(settings, "openrouter_model", "openrouter/free")
    provider = _build("openrouter")
    assert isinstance(provider, OpenRouterProvider)
