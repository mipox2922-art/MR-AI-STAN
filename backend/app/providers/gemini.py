import logging
from typing import Optional

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from .base import AIProvider, AIProviderError
from app.config import settings

logger = logging.getLogger("mrai.providers.gemini")

DEFAULT_MODEL = settings.gemini_model


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self):
        api_key = settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY haipo kwenye .env — Gemini provider haiwezi kuanzishwa.")
        self._client = genai.Client(api_key=api_key)
        self._model = DEFAULT_MODEL

    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction or "You are MR AI, Boss Ferisi's digital chief of staff.",
            temperature=0.7,
            max_output_tokens=2048,
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
        except genai_errors.APIError as e:
            logger.error("Gemini API error [%s]: %s", e.code, e.message)
            raise AIProviderError("gemini", f"API error {e.code}: {e.message}") from e
        except Exception as e:
            logger.exception("Gemini unexpected failure")
            raise AIProviderError("gemini", f"unexpected failure: {e}") from e

        text = getattr(response, "text", None)
        if text:
            return text.strip()

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            raise AIProviderError("gemini", "no candidates returned (likely blocked by safety filters or quota)")

        finish_reason = getattr(candidates[0], "finish_reason", "UNKNOWN")
        parts = getattr(candidates[0].content, "parts", None) if candidates[0].content else None
        if parts:
            joined = "".join(getattr(p, "text", "") or "" for p in parts).strip()
            if joined:
                return joined

        raise AIProviderError("gemini", f"empty response (finish_reason={finish_reason})")
