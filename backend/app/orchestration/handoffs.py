from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus


_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def build_browser_handoff(request: str) -> dict[str, Any] | None:
    """Translate explicit low-risk web intents into Browser Hands operations."""
    value = request.strip()
    lower = value.casefold()

    if any(key in lower for key in ("soma ukurasa", "read page", "angalia ukurasa", "onyesha page")):
        return {
            "action": "GET_PAGE_DATA",
            "payload": {},
            "reason": "Explicit request to read the current browser page.",
        }

    url_match = _URL_RE.search(value)
    open_words = ("fungua", "open", "navigate", "nenda", "visit", "tembelea")
    if url_match and any(key in lower for key in open_words):
        url = url_match.group(0).rstrip(".,);")
        return {
            "action": "NAVIGATE",
            "payload": {"url": url},
            "reason": "Explicit HTTP(S) navigation request.",
        }

    search_words = ("tafuta", "search", "research", "jua kuhusu", "nipe taarifa")
    if any(key in lower for key in search_words):
        query = value
        for prefix in ("tafuta", "search", "research", "jua kuhusu", "nipe taarifa"):
            if lower.startswith(prefix):
                query = value[len(prefix):].strip(" :,-")
                break
        if query:
            return {
                "action": "NAVIGATE",
                "payload": {
                    "url": f"https://www.google.com/search?q={quote_plus(query)}",
                },
                "reason": "Explicit web-search request routed through the authorized browser as a fallback when a dedicated search backend is unavailable.",
            }

    return None
