from .gemini import GeminiProvider
from .kimi import KimiProvider


def get_provider(name: str):
    name = name.lower()

    if name == "gemini":
        return GeminiProvider()

    if name == "kimi":
        return KimiProvider()

    raise ValueError(f"Unsupported AI provider: {name}")
