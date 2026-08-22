import logging
from typing import Optional

from .base import AIProvider, AIProviderError
from .gemini import GeminiProvider
from .kimi import KimiProvider

logger = logging.getLogger("mrai.providers.factory")

_PROVIDERS: dict[str, AIProvider] = {}


def _build(name: str) -> AIProvider:
    if name == "gemini":
        return GeminiProvider()
    if name == "kimi":
        return KimiProvider()
    raise ValueError(f"Unknown AI provider: {name}")


def get_provider(name: str) -> AIProvider:
    if name not in _PROVIDERS:
        _PROVIDERS[name] = _build(name)
    return _PROVIDERS[name]


async def generate_with_fallback(
    prompt: str,
    primary: str = "gemini",
    secondary: str = "kimi",
    system_instruction: Optional[str] = None,
) -> tuple[str, str]:
    errors = []
    for name in (primary, secondary):
        try:
            provider = get_provider(name)
            text = await provider.generate(prompt, system_instruction=system_instruction)
            return text, name
        except (AIProviderError, RuntimeError) as e:
            logger.warning("Provider '%s' failed: %s", name, e)
            errors.append(f"{name}: {e}")

    raise RuntimeError("AI providers zote mbili zimeshindwa -> " + " | ".join(errors))
