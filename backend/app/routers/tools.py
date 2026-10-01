from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..dependencies import get_current_user
from ..tools.registry import registry_summary

router = APIRouter(prefix="/tools", tags=["Tools"])

@router.get("")
def list_tools(current_user=Depends(get_current_user)) -> dict[str, Any]:
    return registry_summary()

@router.post("/search")
async def search_web(payload: dict[str, Any], current_user=Depends(get_current_user)) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    if not settings.searxng_url:
        return {
            "status": "NOT_CONNECTED",
            "query": query,
            "results": [],
            "message": "Configure SEARXNG_URL to connect a self-hosted SearXNG instance.",
        }

    endpoint = settings.searxng_url.rstrip("/") + "/search"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(
                endpoint,
                params={"q": query, "format": "json"},
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"SearXNG search failed: {type(exc).__name__}")

    results = []
    for item in data.get("results", [])[:20]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "engine": item.get("engine", ""),
        })

    return {
        "status": "COMPLETED",
        "query": query,
        "results": results,
        "source": "configured_searxng",
    }
