import logging
from typing import Optional

import httpx

from .base import AIProvider, AIProviderError
from app.config import settings

logger = logging.getLogger("mrai.providers.openrouter")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = settings.openrouter_model


class OpenRouterProvider(AIProvider):
    name = "openrouter"

    def __init__(self):
        api_key = settings.openrouter_api_key.strip()
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY haipo kwenye Render Environment — OpenRouter provider haiwezi kuanzishwa."
            )
        self._api_key = api_key
        self._model = settings.openrouter_model.strip() or DEFAULT_MODEL

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
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://mr-ai-stan-web.onrender.com",
                        "X-Title": "MR AI STAN",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": 0.6,
                        "max_tokens": 2048,
                    },
                )
        except httpx.RequestError as exc:
            logger.warning("OpenRouter connection failed: %s", type(exc).__name__)
            raise AIProviderError("openrouter", "connection failed while calling OpenRouter API") from exc

        if response.status_code == 429:
            raise AIProviderError("openrouter", "rate limit / quota exceeded")
        if response.is_error:
            try:
                payload = response.json()
                detail = str((payload.get("error") or {}).get("message") or response.text[:500])
            except (ValueError, AttributeError):
                detail = response.text[:500]
            # Never log the API key. Only provider response details are logged.
            logger.error("OpenRouter API error [%s]: %s", response.status_code, detail)
            raise AIProviderError("openrouter", f"API error {response.status_code}: {detail}")

        try:
            payload = response.json()
            choices = payload.get("choices") or []
            message = (choices[0].get("message") or {}) if choices else {}
            content = message.get("content")
        except (ValueError, AttributeError, IndexError, TypeError) as exc:
            raise AIProviderError("openrouter", "API returned an invalid response") from exc

        # OpenAI-compatible providers normally return a string, but some
        # OpenRouter routes return multimodal/content-block arrays. Extract text
        # blocks instead of rejecting a usable answer as "empty".
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
        if not isinstance(content, str) or not content.strip():
            finish_reason = (choices[0] or {}).get("finish_reason", "UNKNOWN") if choices else "UNKNOWN"
            refusal = message.get("refusal") if isinstance(message, dict) else None
            if refusal:
                raise AIProviderError("openrouter", f"model refused request: {str(refusal)[:200]}")
            raise AIProviderError("openrouter", f"empty content (finish_reason={finish_reason})")

        return content.strip()
