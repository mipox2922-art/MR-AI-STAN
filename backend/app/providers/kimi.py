import logging
from typing import Optional

import httpx

from .base import AIProvider, AIProviderError
from app.config import settings

logger = logging.getLogger("mrai.providers.kimi")

KIMI_BASE_URL = settings.kimi_base_url.rstrip("/")
DEFAULT_MODEL = settings.kimi_model


class KimiProvider(AIProvider):
    name = "kimi"

    def __init__(self):
        api_key = settings.kimi_api_key
        if not api_key:
            raise RuntimeError("KIMI_API_KEY haipo kwenye .env — Kimi provider haiwezi kuanzishwa.")
        self._api_key = api_key
        self._model = DEFAULT_MODEL

    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        messages = [
            {
                "role": "system",
                "content": system_instruction or "You are MR AI, Boss Ferisi's digital chief of staff.",
            },
            {"role": "user", "content": prompt},
        ]
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{KIMI_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": 0.6,
                        "max_completion_tokens": 2048,
                    },
                )
        except httpx.RequestError as exc:
            logger.warning("Kimi connection failed: %s", type(exc).__name__)
            raise AIProviderError("kimi", "connection failed while calling Kimi API") from exc

        if response.status_code == 429:
            raise AIProviderError("kimi", "rate limit / quota exceeded")
        if response.is_error:
            try:
                payload = response.json()
                detail = str((payload.get("error") or {}).get("message") or response.text[:500])
            except (ValueError, AttributeError):
                detail = response.text[:500]
            logger.error("Kimi API error [%s]: %s", response.status_code, detail)
            raise AIProviderError("kimi", f"API error {response.status_code}: {detail}")

        try:
            payload = response.json()
            choices = payload.get("choices") or []
            content = (choices[0].get("message") or {}).get("content") if choices else None
        except (ValueError, AttributeError, IndexError, TypeError) as exc:
            raise AIProviderError("kimi", "API returned an invalid response") from exc

        if not isinstance(content, str) or not content.strip():
            finish_reason = (choices[0] or {}).get("finish_reason", "UNKNOWN") if choices else "UNKNOWN"
            raise AIProviderError("kimi", f"empty content (finish_reason={finish_reason})")

        return content.strip()
