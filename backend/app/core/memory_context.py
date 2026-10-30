from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import Memory

_SECRET_KEY = re.compile(
    r"(password|passcode|secret|api.?key|access.?token|refresh.?token|otp|pin|private.?key|credential|recovery.?code)",
    re.I,
)
_SECRET_VALUE = re.compile(
    r"(?:bearer\\s+[a-z0-9._-]{16,}|sk-[a-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,})",
    re.I,
)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "for",
    "from", "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "please",
    "the", "this", "to", "we", "what", "when", "where", "which", "who", "why",
    "you", "your", "na", "ni", "ya", "za", "kwa", "kwenye", "hii", "huyo", "hiyo",
    "nini", "gani", "vipi", "je", "kaka", "boss", "mr", "ai", "tafadhali",
}


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-zA-ZÀ-ÿ0-9_+-]{2,}", str(value or "").casefold())
        if token not in _STOP_WORDS
    }


def _safe_for_model(row: Memory) -> bool:
    key = str(row.key or "")
    value = str(row.value or "")
    if _SECRET_KEY.search(key):
        return False
    if _SECRET_VALUE.search(value):
        return False
    return True


def recall_relevant_memories(
    db: Session,
    user_id: int,
    query: str,
    *,
    limit: int = 6,
    max_value_chars: int = 1200,
) -> list[dict[str, Any]]:
    """Return a small, owner-scoped set of memories relevant to the current request.

    Secrets are excluded. Memory content is returned as untrusted data and must
    never be interpreted as instructions by an AI model or execution tool.
    """
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    rows = (
        db.query(Memory)
        .filter(Memory.user_id == user_id)
        .order_by(Memory.updated_at.desc(), Memory.id.desc())
        .limit(250)
        .all()
    )
    ranked: list[tuple[int, int, Memory]] = []
    query_text = str(query or "").casefold()
    for row in rows:
        if not _safe_for_model(row):
            continue
        key_tokens = _tokens(row.key)
        value_tokens = _tokens(row.value)
        overlap = query_tokens & (key_tokens | value_tokens)
        if not overlap:
            continue
        score = len(overlap) + (2 * len(query_tokens & key_tokens))
        combined = f"{row.key} {row.value}".casefold()
        if query_text and len(query_text) >= 5 and query_text in combined:
            score += 4
        ranked.append((score, int(row.id or 0), row))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    result = []
    for score, _row_id, row in ranked[:max(1, min(int(limit), 12))]:
        value = str(row.value or "").strip()
        if not value:
            continue
        result.append({
            "id": row.id,
            "key": str(row.key or "")[:255],
            "value": value[:max(100, min(int(max_value_chars), 2000))],
            "relevance": score,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        })
    return result
