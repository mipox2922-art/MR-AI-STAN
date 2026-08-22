from abc import ABC, abstractmethod
from typing import Optional


class AIProviderError(Exception):
    """Raised when an AI provider fails to return a usable response."""
    def __init__(self, provider: str, detail: str):
        self.provider = provider
        self.detail = detail
        super().__init__(f"[{provider}] {detail}")


class AIProvider(ABC):
    name: str

    @abstractmethod
    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Return plain text reply. Must raise AIProviderError on failure — never return None/empty silently."""
        raise NotImplementedError
