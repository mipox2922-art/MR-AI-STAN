from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

# Process-local circuit breaker. It deliberately keeps only safe diagnostics,
# never prompts, API keys, response bodies or provider request payloads.
_LOCK = threading.RLock()
_COOLDOWNS: dict[str, float] = {}
_LAST_FAILURE: dict[str, dict[str, str]] = {}
_FAILURE_COUNTS: dict[str, int] = {}

_RATE_LIMIT = re.compile(r"\\b(429|rate.?limit|too many requests|quota|resource exhausted)\\b", re.I)
_AUTH_FAILURE = re.compile(r"\\b(401|403|unauthorized|invalid api.?key|permission denied)\\b", re.I)
_SERVER_FAILURE = re.compile(r"\\b(500|502|503|504|timeout|timed out|connection|temporarily unavailable)\\b", re.I)


def _safe_detail(error: BaseException) -> str:
    raw = str(getattr(error, "detail", None) or error or type(error).__name__)
    value = re.sub(r"(?i)bearer\\s+[^\\s,;]+", "Bearer [redacted]", raw)
    value = re.sub(r"(?i)(api[_-]?key|token|secret)(\\s*[:=]\\s*)[^\\s,;]+", r"\\1\\2[redacted]", value)
    return value[:240]


def classify_provider_failure(error: BaseException) -> tuple[str, int]:
    detail = _safe_detail(error)
    if _RATE_LIMIT.search(detail):
        return "RATE_LIMIT", 120
    if _AUTH_FAILURE.search(detail):
        return "AUTH_OR_PERMISSION", 600
    if _SERVER_FAILURE.search(detail) or isinstance(error, TimeoutError):
        return "TEMPORARY_UPSTREAM_FAILURE", 30
    return "PROVIDER_FAILURE", 15


def provider_is_cooling_down(name: str) -> bool:
    now = time.monotonic()
    key = str(name or "").strip().lower()
    with _LOCK:
        until = _COOLDOWNS.get(key, 0.0)
        if until <= now:
            _COOLDOWNS.pop(key, None)
            return False
        return True


def seconds_until_retry(name: str) -> int:
    key = str(name or "").strip().lower()
    with _LOCK:
        return max(0, int(_COOLDOWNS.get(key, 0.0) - time.monotonic() + 0.999))


def record_provider_success(name: str) -> None:
    key = str(name or "").strip().lower()
    if not key:
        return
    with _LOCK:
        _COOLDOWNS.pop(key, None)
        _LAST_FAILURE.pop(key, None)
        _FAILURE_COUNTS.pop(key, None)


def record_provider_failure(name: str, error: BaseException) -> dict[str, Any]:
    key = str(name or "").strip().lower()
    category, cooldown_seconds = classify_provider_failure(error)
    now = time.monotonic()
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)
    with _LOCK:
        _COOLDOWNS[key] = now + cooldown_seconds
        _FAILURE_COUNTS[key] = _FAILURE_COUNTS.get(key, 0) + 1
        _LAST_FAILURE[key] = {
            "category": category,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "retry_at": retry_at.isoformat(),
        }
    return {"category": category, "cooldown_seconds": cooldown_seconds}


def provider_runtime_snapshot(configured: dict[str, bool]) -> list[dict[str, Any]]:
    now_mono = time.monotonic()
    now_utc = datetime.now(timezone.utc)
    rows = []
    with _LOCK:
        for name, is_configured in configured.items():
            key = name.casefold()
            until = _COOLDOWNS.get(key, 0.0)
            retry_after = max(0, int(until - now_mono + 0.999)) if until > now_mono else 0
            if until and retry_after == 0:
                _COOLDOWNS.pop(key, None)
                _LAST_FAILURE.pop(key, None)
                _FAILURE_COUNTS.pop(key, None)
            last = _LAST_FAILURE.get(key)
            rows.append({
                "provider": key,
                "configured": bool(is_configured),
                "status": (
                    "NOT_CONFIGURED" if not is_configured
                    else "COOLDOWN" if retry_after > 0
                    else "READY"
                ),
                "retry_after_seconds": retry_after,
                "last_failure": last["category"] if last else None,
                "last_failure_at": last["occurred_at"] if last else None,
                "failure_count": _FAILURE_COUNTS.get(key, 0),
            })
    return rows


def reset_provider_runtime_state() -> None:
    """Test helper. Not exposed through an HTTP endpoint."""
    with _LOCK:
        _COOLDOWNS.clear()
        _LAST_FAILURE.clear()
        _FAILURE_COUNTS.clear()
