import pytest

from app.config import settings
from app.providers.factory import _build
from app.providers.grok import GrokProvider
from app.providers.mistral import MistralProvider


@pytest.mark.parametrize(
    ("provider_class", "setting"),
    [
        (MistralProvider, "mistral_api_key"),
        (GrokProvider, "xai_api_key"),
    ],
)
def test_provider_requires_server_side_key(monkeypatch, provider_class, setting):
    monkeypatch.setattr(settings, setting, "")
    with pytest.raises(RuntimeError, match="API_KEY"):
        provider_class()


@pytest.mark.parametrize(
    ("provider_name", "setting", "provider_class"),
    [
        ("mistral", "mistral_api_key", MistralProvider),
        ("grok", "xai_api_key", GrokProvider),
    ],
)
def test_factory_builds_provider_when_selected(monkeypatch, provider_name, setting, provider_class):
    monkeypatch.setattr(settings, setting, "test-key-not-real")
    assert isinstance(_build(provider_name), provider_class)
