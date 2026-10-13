from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .models import ActivityLog, Notification, Setting, User

logger = logging.getLogger("mr_ai.self_audit")
AUDIT_INTERVAL_SECONDS = 15 * 60
AUDIT_KEY = "system_self_audit"
_last_audit_monotonic = 0.0


def _provider_names() -> list[str]:
    providers = {
        "OpenRouter": settings.openrouter_api_key,
        "Gemini": settings.gemini_api_key,
        "Kimi": settings.kimi_api_key,
        "Mistral": settings.mistral_api_key,
        "Grok": settings.xai_api_key,
    }
    return [name for name, key in providers.items() if bool(str(key or "").strip())]


def _collect_report(db: Session) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1")).scalar_one()
        database_ok = True
        database_detail = "Database query succeeded."
    except Exception as exc:
        db.rollback()
        database_ok = False
        database_detail = f"Database query failed ({type(exc).__name__})."

    providers = _provider_names()
    scheduler_running_by_config = settings.scheduler_enabled and not settings.serverless_mode
    gmail_configured = all((
        settings.gmail_client_id.strip(),
        settings.gmail_client_secret.strip(),
        settings.gmail_redirect_uri.strip(),
    ))

    checks = [
        {
            "id": "database",
            "label": "Database",
            "status": "PASS" if database_ok else "FAIL",
            "detail": database_detail,
        },
        {
            "id": "ai_provider",
            "label": "AI provider",
            "status": "KEY_PRESENT_NOT_LIVE_TESTED" if providers else "MISSING",
            "detail": (
                "Provider key(s) present: " + ", ".join(providers) +
                ". Key presence does not prove a live model request succeeds."
                if providers else
                "No AI provider key is configured; model chat cannot run until a provider key is added."
            ),
        },
        {
            "id": "scheduler",
            "label": "Background scheduler",
            "status": "ENABLED_BY_CONFIG" if scheduler_running_by_config else "DISABLED",
            "detail": (
                "The in-process worker is enabled while the Render instance is awake."
                if scheduler_running_by_config else
                "Background scheduler is disabled by runtime configuration."
            ),
        },
        {
            "id": "gmail",
            "label": "Gmail integration",
            "status": "OAUTH_CONFIGURED_NOT_AUTHORIZED" if gmail_configured else "OPTIONAL_NOT_CONFIGURED",
            "detail": (
                "OAuth settings are present, but mailbox access still needs an authorization check."
                if gmail_configured else
                "Optional integration. Gmail actions require OAuth configuration and user authorization."
            ),
        },
        {
            "id": "web_search",
            "label": "General web search",
            "status": "CONFIGURED" if settings.searxng_url.strip() else "OPTIONAL_NOT_CONFIGURED",
            "detail": (
                "SearXNG URL is configured; reachability is not tested by this self-check."
                if settings.searxng_url.strip() else
                "SearXNG is optional; Job Research uses separate public feeds."
            ),
        },
        {
            "id": "device_bridge",
            "label": "Owner PC / device bridge",
            "status": "LOCAL_CHECK_REQUIRED",
            "detail": "A hosted backend cannot verify a bridge running on the owner's own PC. Check it from the local dashboard.",
        },
        {
            "id": "gpu",
            "label": "GPU telemetry",
            "status": "NOT_AVAILABLE_ON_HOST" ,
            "detail": "GPU usage is shown only when the hosted runtime exposes a supported GPU sensor.",
        },
    ]

    blockers = []
    if not database_ok:
        blockers.append({"id": "database", "message": "Database check failed."})
    if not providers:
        blockers.append({"id": "ai_provider", "message": "No AI provider key is configured, so live AI chat is unavailable."})
    if not scheduler_running_by_config:
        blockers.append({"id": "scheduler", "message": "Background scheduler is disabled by configuration."})

    status = "DEGRADED" if blockers else "CONFIGURATION_OK_UNTESTED"
    summary = {
        "status": status,
        "checks": checks,
        "blockers": blockers,
        "truth_boundary": (
            "This is a configuration/database self-check, not a live test of provider APIs, "
            "Gmail OAuth, browser extension, owner PC sensors, GPU, or external actions. "
            "On Render's free service, background checks pause while the instance is asleep."
        ),
    }
    signature = hashlib.sha256(
        json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        **summary,
        "signature": signature,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def run_self_audit(db: Session) -> dict[str, Any]:
    """Check runtime readiness, persist the latest snapshot, and alert only on changes."""
    report = _collect_report(db)
    users = db.query(User).order_by(User.id.asc()).all()
    changed_users = 0

    for user in users:
        setting = (
            db.query(Setting)
            .filter(Setting.user_id == user.id, Setting.key == AUDIT_KEY)
            .order_by(Setting.id.desc())
            .first()
        )
        previous: dict[str, Any] = {}
        if setting and setting.value:
            try:
                previous = json.loads(setting.value)
            except (TypeError, ValueError):
                previous = {}

        changed = previous.get("signature") != report["signature"]
        previous_blockers = previous.get("blockers") or []
        current_blockers = report["blockers"]

        if setting is None:
            setting = Setting(user_id=user.id, key=AUDIT_KEY, value="")
            db.add(setting)
        setting.value = json.dumps(report, ensure_ascii=False, separators=(",", ":"))

        if not changed:
            continue

        changed_users += 1
        blocker_titles = "; ".join(item["message"] for item in current_blockers)
        db.add(ActivityLog(
            user_id=user.id,
            action="SYSTEM_SELF_AUDIT",
            details=f'{report["status"]}: {blocker_titles or "Required runtime checks passed."}',
        ))

        if current_blockers and current_blockers != previous_blockers:
            db.add(Notification(
                user_id=user.id,
                title="MR AI self-check needs attention",
                message="; ".join(item["message"] for item in current_blockers),
                read=False,
            ))
        elif previous_blockers and not current_blockers:
            db.add(Notification(
                user_id=user.id,
                title="MR AI configuration checks recovered",
                message="Required configuration checks now pass. The provider key is present but live model calls, Gmail OAuth, and external integrations still need verification.",
                read=False,
            ))

    if users:
        db.commit()
    else:
        db.rollback()

    return {
        "status": report["status"],
        "checked_users": len(users),
        "changed_users": changed_users,
        "blockers": report["blockers"],
        "checked_at": report["checked_at"],
    }


def maybe_run_self_audit(db: Session, *, force: bool = False) -> dict[str, Any] | None:
    """Run at most once per interval in this process; safe to call per scheduler tick."""
    global _last_audit_monotonic
    now = time.monotonic()
    if not force and now - _last_audit_monotonic < AUDIT_INTERVAL_SECONDS:
        return None

    _last_audit_monotonic = now
    try:
        report = run_self_audit(db)
        logger.info(
            "Runtime self-audit: status=%s users=%s changed=%s blockers=%s",
            report["status"],
            report["checked_users"],
            report["changed_users"],
            len(report["blockers"]),
        )
        return report
    except Exception:
        _last_audit_monotonic = 0.0
        db.rollback()
        logger.exception("Runtime self-audit failed")
        return None
