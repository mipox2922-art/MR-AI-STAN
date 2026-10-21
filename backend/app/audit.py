"""Safe error/event helpers. Never pass user message content or credentials here."""
from __future__ import annotations

import re
from sqlalchemy.orm import Session

from .models import ActivityLog, SystemErrorLog


_SECRET_PATTERNS = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-=]+"), "Bearer [REDACTED]"),
    (re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{25,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bxai-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
    (
        re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[^\s,;]+"),
        r"\1=[REDACTED]",
    ),
)


def redact_sensitive_text(value: object, limit: int = 500) -> str:
    safe = str(value or "")
    for pattern, replacement in _SECRET_PATTERNS:
        safe = pattern.sub(replacement, safe)
    return safe[:limit]


def record_safe_error(
    db: Session,
    user_id: int | None,
    component: str,
    code: str,
    message_safe: str,
) -> None:
    """Persist redacted summaries only; never record prompts, headers, or raw request bodies."""
    try:
        safe_component = redact_sensitive_text(component, 100)
        safe_code = redact_sensitive_text(code, 100)
        safe_message = redact_sensitive_text(message_safe, 500)
        db.add(SystemErrorLog(
            user_id=user_id,
            component=safe_component,
            code=safe_code,
            message_safe=safe_message,
        ))
        if user_id is not None:
            db.add(ActivityLog(
                user_id=user_id,
                action="SYSTEM_ERROR",
                details=redact_sensitive_text(
                    f"{safe_component}:{safe_code}; {safe_message}", 500
                ),
            ))
        db.commit()
    except Exception:
        db.rollback()
