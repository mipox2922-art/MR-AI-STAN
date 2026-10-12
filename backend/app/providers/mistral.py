import logging
from typing import Optional

import httpx

from .base import AIProvider, AIProviderError
from app.config import settings

logger = logging.getLogger("mrai.providers.mistral")

MISTRAL_BASE_URL = "https://api.mistral.ai/v1"


class MistralProvider(AIProvider):
    name = "mistral"

    def __init__(self):
        api_key = settings.mistral_api_key.strip()
        if not api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY haipo kwenye Render Environment — Mistral provider haiwezi kuanzishwa."
            )
        self._api_key = api_key
        self._model = settings.mistral_model.strip()

    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        messages = [
            {
                "role": "system",
                "content": system_instruction or "You are MR AI, Boss Ferisi's digital chief of staff. Reply naturally in Swahili.",
            },
            {"role": "user", "content": prompt},
        ]
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{MISTRAL_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": 0.6,
                        "max_tokens": 2048,
                    },
                )
        except httpx.RequestError as exc:
            logger.warning("Mistral connection failed: %s", type(exc).__name__)
            raise AIProviderError("mistral", "connection failed while calling Mistral API") from exc

        if response.status_code == 429:
            raise AIProviderError("mistral", "rate limit / quota exceeded")
        if response.is_error:
            try:
                payload = response.json()
                error = payload.get("error") or {}
                detail = str(error.get("message") if isinstance(error, dict) else error)
                detail = detail if detail and detail != "None" else response.text[:500]
            except (ValueError, AttributeError):
                detail = response.text[:500]
            logger.error("Mistral API error [%s]: %s", response.status_code, detail)
            raise AIProviderError("mistral", f"API error {response.status_code}: {detail}")

        try:
            payload = response.json()
            choices = payload.get("choices") or []
            content = (choices[0].get("message") or {}).get("content") if choices else None
        except (ValueError, AttributeError, IndexError, TypeError) as exc:
            raise AIProviderError("mistral", "API returned an invalid response") from exc

        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("mistral", "API returned empty content")

        return content.strip()
