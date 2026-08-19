from abc import ABC, abstractmethod


class AIProviderError(Exception):
    """Base exception for all AI provider failures (API errors, bad responses, etc.)."""
    def __init__(self, message: str, provider: str = "unknown"):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class AIProviderTimeout(AIProviderError):
    """Raised when a provider request exceeds the allowed time limit."""
    pass


class AIProvider(ABC):
    name: str = "unknown"

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError
