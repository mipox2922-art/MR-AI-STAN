from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus


_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_CLICK_RE = re.compile(r"^(?:bonyeza|click)\s+(?:(?:element|selector)\s+)?(.+)$", re.IGNORECASE)
_TYPE_RE = re.compile(r"^(?:andika|type|weka|jaza)\s+(?:kwenye|into)?\s*(\S+)\s*[:=]\s*(.+)$", re.IGNORECASE)
_SCROLL_RE = re.compile(r"^(?:scroll|sogeza)(?:\s+(up|down|juu|chini))?(?:\s+(\d+))?$", re.IGNORECASE)
_DRAG_RE = re.compile(r"^drag\s+(\S+)\s+(-?\d+)\s+(-?\d+)$", re.IGNORECASE)


def _is_high_risk_browser_request(value: str) -> bool:
    risky_terms = (
        "submit", "send", "tuma", "delete", "futa", "remove", "checkout",
        "purchase", "buy", "pay", "login", "log in", "sign in",
    )
    return any(term in value.casefold() for term in risky_terms)


def build_browser_handoff(request: str) -> dict[str, Any] | None:
    """Translate explicit browser intents into authorized Browser Hands operations.

    The parser only creates low-risk handoffs. Potentially consequential operations
    such as submit/send/delete/purchase/login stay outside automatic handoff.
    """
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

    click = _CLICK_RE.match(value)
    if click and not _is_high_risk_browser_request(value):
        selector = click.group(1).strip()
        if selector.startswith(("#", ".", "[", "button", "input", "a", "textarea", "select")):
            return {
                "action": "CLICK",
                "payload": {"selector": selector},
                "reason": "Explicit low-risk selector-based browser click.",
            }

    typed = _TYPE_RE.match(value)
    if typed and not _is_high_risk_browser_request(value):
        selector, text = typed.groups()
        return {
            "action": "TYPE",
            "payload": {"selector": selector.strip(), "value": text.strip()},
            "reason": "Explicit low-risk selector-based text entry.",
        }

    scrolled = _SCROLL_RE.match(value)
    if scrolled:
        direction, amount = scrolled.groups()
        pixels = int(amount or 700)
        if direction and direction.casefold() in {"up", "juu"}:
            pixels = -pixels
        return {
            "action": "SCROLL",
            "payload": {"amount": pixels},
            "reason": "Explicit browser scroll request.",
        }

    dragged = _DRAG_RE.match(value)
    if dragged and not _is_high_risk_browser_request(value):
        selector, dx, dy = dragged.groups()
        return {
            "action": "DRAG",
            "payload": {
                "selector": selector,
                "dx": int(dx),
                "dy": int(dy),
            },
            "reason": "Explicit selector-based browser drag request.",
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
