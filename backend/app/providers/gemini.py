import httpx
from .base import AIProvider
from ..config import settings


class GeminiProvider(AIProvider):
    name = "gemini"

    async def generate(self, prompt: str) -> str:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{settings.gemini_model}:generateContent"
        )
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
        }
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "You are MR AI, the Digital Chief of Staff "
                                "for Boss Ferisi. "
                                "Reply naturally in Swahili. "
                                "Be short, useful, confident and friendly. "
                                "Never claim an action happened unless verified. "
                                f"Boss says: {prompt}"
                            )
                        }
                    ]
                }
            ]
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            print("===== GEMINI API ERROR =====", flush=True)
            print(f"STATUS: {response.status_code}", flush=True)
            print(f"BODY: {response.text}", flush=True)
            raise RuntimeError(
                f"Gemini API HTTP {response.status_code}: {response.text}"
            )

        data = response.json()
        if "candidates" not in data or not data["candidates"]:
            raise RuntimeError(f"Gemini returned unexpected response: {data}")

        return data["candidates"][0]["content"]["parts"][0]["text"]
