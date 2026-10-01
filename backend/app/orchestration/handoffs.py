from __future__ import annotations

import re
from typing import Any


_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def build_browser_handoff(request: str) -> dict[str, Any] | None:
    """Translate only explicit, low-risk browser intents into a browser handoff."""
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

    return None
