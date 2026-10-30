from __future__ import annotations

import asyncio
import re
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx

USER_AGENT = "MR-AI-STAN public research client"


def _clean(value: Any, maximum: int = 1000) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:maximum]


async def _wikipedia(client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, Any]]:
    response = await client.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "list": "search", "srsearch": query,
                "srnamespace": 0, "srlimit": min(limit, 8), "format": "json"},
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    hits = ((response.json().get("query") or {}).get("search") or [])
    return [{
        "title": _clean(hit.get("title"), 240),
        "url": "https://en.wikipedia.org/wiki/" + quote(str(hit.get("title") or "").replace(" ", "_"), safe="()_-"),
        "content": _clean(hit.get("snippet"), 900),
        "source": "Wikipedia",
        "published_at": None,
    } for hit in hits if hit.get("title")]


async def _hacker_news(client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, Any]]:
    response = await client.get(
        "https://hn.algolia.com/api/v1/search",
        params={"query": query, "tags": "story", "hitsPerPage": min(limit, 8)},
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    hits = response.json().get("hits") or []
    results = []
    for hit in hits:
        title = _clean(hit.get("title") or hit.get("story_title"), 240)
        story_id = str(hit.get("objectID") or "").strip()
        url = str(hit.get("url") or "").strip()
        if not url and story_id:
            url = "https://news.ycombinator.com/item?id=" + quote(story_id)
        if title and url.startswith("https://"):
            results.append({
                "title": title,
                "url": url,
                "content": _clean(hit.get("story_text"), 900),
                "source": "Hacker News",
                "published_at": hit.get("created_at"),
                "points": hit.get("points"),
            })
    return results


async def search_public_sources(query: str, limit: int = 12) -> dict[str, Any]:
    """Bounded no-key fallback: Wikipedia and Hacker News public read APIs."""
    normalized = str(query or "").strip()[:300]
    if not normalized:
        return {"status": "REJECTED", "query": normalized, "results": [], "sources": [], "source_warnings": ["Query is empty."]}

    max_results = max(1, min(int(limit), 20))
    timeout = httpx.Timeout(8.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        responses = await asyncio.gather(
            _wikipedia(client, normalized, max_results),
            _hacker_news(client, normalized, max_results),
            return_exceptions=True,
        )

    results: dict[str, dict[str, Any]] = {}
    sources = []
    warnings = []
    for name, response in zip(("Wikipedia", "Hacker News"), responses):
        if isinstance(response, BaseException):
            warnings.append(name + ": " + type(response).__name__)
            continue
        sources.append(name)
        for item in response:
            url = str(item.get("url") or "").strip()
            if url.startswith("https://"):
                results.setdefault(url.casefold(), item)

    items = list(results.values())[:max_results]
    status = "SOURCE_ERROR" if not sources else "COMPLETED" if items else "NO_RESULTS"
    return {
        "status": status,
        "query": normalized,
        "count": len(items),
        "results": items,
        "sources": sources,
        "source_warnings": warnings,
        "source_mode": "public_api_fallback",
        "limitations": [
            "SearXNG is not configured; this fallback searches Wikipedia and Hacker News only.",
            "Open source URLs and check publication date and context before relying on a result.",
        ],
    }
