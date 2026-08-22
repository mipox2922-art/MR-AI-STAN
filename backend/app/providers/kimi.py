import logging
from typing import Optional

from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError

from .base import AIProvider, AIProviderError
from app.config import settings

logger = logging.getLogger("mrai.providers.kimi")

KIMI_BASE_URL = settings.kimi_base_url
DEFAULT_MODEL = settings.kimi_model


class KimiProvider(AIProvider):
    name = "kimi"

    def __init__(self):
        api_key = settings.kimi_api_key
        if not api_key:
            raise RuntimeError("KIMI_API_KEY haipo kwenye .env — Kimi provider haiwezi kuanzishwa.")
        self._client = AsyncOpenAI(api_key=api_key, base_url=KIMI_BASE_URL)
        self._model = DEFAULT_MODEL

    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        messages = [
            {"role": "system", "content": system_instruction or "You are MR AI, Boss Ferisi's digital chief of staff."},
            {"role": "user", "content": prompt},
        ]
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.6,
                max_completion_tokens=2048,
            )
        except RateLimitError as e:
            raise AIProviderError("kimi", f"rate limit / quota exceeded: {e}") from e
        except APIConnectionError as e:
            raise AIProviderError("kimi", f"connection failed (network/firewall?): {e}") from e
        except APIError as e:
            logger.error("Kimi API error: %s", e)
            raise AIProviderError("kimi", f"API error: {e}") from e
        except Exception as e:
            logger.exception("Kimi unexpected failure")
            raise AIProviderError("kimi", f"unexpected failure: {e}") from e

        if not response.choices:
            raise AIProviderError("kimi", "no choices returned")

        content = response.choices[0].message.content
        if not content or not content.strip():
            finish_reason = response.choices[0].finish_reason
            raise AIProviderError("kimi", f"empty content (finish_reason={finish_reason})")

        return content.strip()
