import httpx

from .base import AIProvider
from ..config import settings


class KimiProvider(AIProvider):

    name = "kimi"

    async def generate(self, prompt: str) -> str:
        if not settings.kimi_api_key:
            raise RuntimeError("KIMI_API_KEY is not configured")

        url = f"{settings.kimi_base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {settings.kimi_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": settings.kimi_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are MR AI, Digital Chief of Staff "
                        "for Boss Ferisi. Reply naturally in Swahili. "
                        "Be short, useful, confident and friendly."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )

        response.raise_for_status()

        data = response.json()

        return data["choices"][0]["message"]["content"]
