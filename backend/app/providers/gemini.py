import logging
from typing import Optional

import httpx

from .base import AIProvider, AIProviderError
from app.config import settings

logger = logging.getLogger("mrai.providers.gemini")

DEFAULT_MODEL = settings.gemini_model
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self):
        api_key = settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY haipo kwenye .env — Gemini provider haiwezi kuanzishwa.")
        self._api_key = api_key
        self._model = DEFAULT_MODEL

    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
            },
        }
        instruction = system_instruction or "You are MR AI, Boss Ferisi's digital chief of staff."
        if instruction:
            payload["systemInstruction"] = {"parts": [{"text": instruction}]}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{GEMINI_API_BASE}/{self._model}:generateContent",
                    headers={"x-goog-api-key": self._api_key},
                    json=payload,
                )
        except httpx.RequestError as exc:
            logger.warning("Gemini connection failed: %s", type(exc).__name__)
            raise AIProviderError("gemini", "connection failed while calling Gemini API") from exc

        if response.is_error:
            try:
                error_payload = response.json().get("error", {})
                detail = str(error_payload.get("message") or response.text[:500])
            except (ValueError, AttributeError):
                detail = response.text[:500]
            logger.error("Gemini API error [%s]: %s", response.status_code, detail)
            raise AIProviderError("gemini", f"API error {response.status_code}: {detail}")

        try:
            result = response.json()
        except ValueError as exc:
            raise AIProviderError("gemini", "API returned invalid JSON") from exc

        candidates = result.get("candidates") or []
        if not candidates:
            raise AIProviderError("gemini", "no candidates returned (likely blocked by safety filters or quota)")

        candidate = candidates[0] or {}
        parts = (candidate.get("content") or {}).get("parts") or []
        answer = "".join(str(part.get("text") or "") for part in parts).strip()
        if answer:
            return answer

        finish_reason = candidate.get("finishReason", "UNKNOWN")
        raise AIProviderError("gemini", f"empty response (finish_reason={finish_reason})")
