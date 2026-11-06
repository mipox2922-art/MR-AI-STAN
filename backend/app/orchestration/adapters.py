from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..config import settings
from ..models import ActivityLog, ScheduledJob
from ..tools.registry import registry_summary

OWNER_TIMEZONE = ZoneInfo("Africa/Dar_es_Salaam")


def _parse_schedule_time(request: str) -> tuple[datetime | None, int | None]:
    """Parse explicit relative/absolute dates and times; never invent a reminder time."""
    value = str(request or "").strip().casefold()
    now = datetime.now(OWNER_TIMEZONE)

    every = re.search(r"\b(?:every|kila)\s+(\d{1,3})?\s*(minutes?|mins?|dakika|hours?|hrs?|saa|days?|siku)\b", value)
    if "kila siku" in value or "every day" in value or "daily" in value:
        interval = 1440
    elif "kila saa" in value or "every hour" in value or "hourly" in value:
        interval = 60
    elif every:
        amount = int(every.group(1) or 1)
        unit = every.group(2)
        if any(token in unit for token in ("minute", "min", "dakika")):
            interval = amount
        elif any(token in unit for token in ("hour", "hr", "saa")):
            interval = amount * 60
        else:
            interval = amount * 1440
        if interval < 1 or interval > 525600:
            return None, None
    else:
        interval = None

    relative = re.search(r"\b(?:in|within|baada\s+ya)\s+(\d{1,4})\s*(minutes?|mins?|dakika|hours?|hrs?|saa)\b", value)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        delta = timedelta(minutes=amount) if any(token in unit for token in ("minute", "min", "dakika")) else timedelta(hours=amount)
        return (now + delta).astimezone(timezone.utc).replace(tzinfo=None), interval

    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})(?:t|\s+)(\d{1,2}):(\d{2})\b", value)
    if iso:
        try:
            local = datetime.fromisoformat(f"{iso.group(1)}T{int(iso.group(2)):02d}:{iso.group(3)}").replace(tzinfo=OWNER_TIMEZONE)
        except ValueError:
            return None, interval
        return local.astimezone(timezone.utc).replace(tzinfo=None), interval

    clock = re.search(r"\b(?:at|saa)\s*(\d{1,2})(?::(\d{2}))?\b", value)
    if clock:
        hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
        if hour > 23 or minute > 59:
            return None, interval
        day = now.date()
        if any(word in value for word in ("tomorrow", "kesho")):
            day += timedelta(days=1)
        local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=OWNER_TIMEZONE)
        if local <= now:
            local += timedelta(days=1)
        return local.astimezone(timezone.utc).replace(tzinfo=None), interval

    return None, interval


def execute_scheduler_request(db: Session, user_id: int, request: str) -> dict[str, Any]:
    """Real DB-backed schedule adapter. Creating a reminder never sends a message."""
    value = str(request or "").strip()
    lowered = value.casefold()
    rows = (
        db.query(ScheduledJob)
        .filter(ScheduledJob.user_id == user_id)
        .order_by(ScheduledJob.next_run_at.asc().nullslast(), ScheduledJob.id.desc())
        .limit(50)
        .all()
    )
    wants_list = any(term in lowered for term in (
        "list", "show", "view", "check", "onyesha", "angalia", "ratiba zangu", "reminders", "ratiba zilizopo"
    ))
    explicit_create = bool(re.search(
        r"\b(?:remind(?: me)?|set (?:a )?reminder|create (?:a )?(?:reminder|schedule)|"
        r"add (?:a )?(?:reminder|schedule)|schedule\s+(?!list\b)|panga|kumbusha|kumbusho)\b",
        lowered,
    ))
    wants_create = explicit_create
    if wants_list and not explicit_create:
        return {
            "status": "COMPLETED",
            "verified": True,
            "tool": "scheduler_database",
            "count": len(rows),
            "schedules": [_schedule_payload(row) for row in rows],
            "message": "Ratiba zimesomwa kutoka kwenye database ya MR AI.",
        }

    run_at, interval = _parse_schedule_time(value)
    if not wants_create:
        return {
            "status": "COMPLETED",
            "verified": True,
            "tool": "scheduler_database",
            "count": len(rows),
            "schedules": [_schedule_payload(row) for row in rows[:20]],
            "message": "Ratiba zilizopo zimesomwa; hakuna schedule mpya iliyoundwa.",
        }
    if run_at is None:
        return {
            "status": "WAITING_FOR_DETAILS",
            "verified": False,
            "tool": "scheduler_database",
            "message": "Nimeelewa kuwa unataka reminder, lakini muda haukutajwa. Hakuna ratiba iliyobuniwa au kuhifadhiwa.",
            "required_detail": "Tarehe na saa ya kukumbushwa, au muda kama 'baada ya dakika 30' / 'kila siku saa 09:00'.",
        }

    title = re.sub(
        r"^(?:(?:please|tafadhali)\s+)?(?:remind me|reminder|remind|kumbusha|kumbusho|schedule|ratiba|panga)\s*(?:me\s*)?(?:to\s*)?",
        "",
        value,
        flags=re.I,
    ).strip(" .,:;-")
    title = re.sub(r"\b(?:tomorrow|kesho|today|leo|at|saa)\s*\d{0,2}(?::\d{2})?\b", "", title, flags=re.I).strip(" .,:;-")
    if not title:
        title = "Owner reminder"
    title = title[:255]
    command = "Reminder only: " + title
    existing = next((
        row for row in rows
        if row.title.casefold() == title.casefold()
        and row.status == "ACTIVE"
        and row.next_run_at == run_at
        and row.interval_minutes == interval
    ), None)
    if existing:
        return {
            "status": "COMPLETED",
            "verified": True,
            "tool": "scheduler_database",
            "schedule": _schedule_payload(existing),
            "idempotent": True,
            "message": "Ratiba hiyo tayari ipo; sikutengeneza duplicate.",
        }

    job = ScheduledJob(
        user_id=user_id,
        title=title,
        command=command,
        status="ACTIVE",
        run_at=run_at,
        interval_minutes=interval,
        next_run_at=run_at,
    )
    db.add(job)
    db.flush()
    db.add(ActivityLog(
        user_id=user_id,
        action="SCHEDULE_CREATED_BY_AGENT",
        details=f"schedule_id={job.id}; source=mission_scheduler; reminder_only=true",
    ))
    db.commit()
    db.refresh(job)
    return {
        "status": "COMPLETED",
        "verified": True,
        "tool": "scheduler_database",
        "schedule": _schedule_payload(job),
        "message": "Reminder imehifadhiwa kwenye MR AI Scheduler. Hakuna email, ujumbe wa nje au malipo yaliyotumwa.",
    }


def _schedule_payload(job: ScheduledJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "title": job.title,
        "status": job.status,
        "run_at_utc": job.run_at.replace(tzinfo=timezone.utc).isoformat() if job.run_at else None,
        "next_run_at_utc": job.next_run_at.replace(tzinfo=timezone.utc).isoformat() if job.next_run_at else None,
        "interval_minutes": job.interval_minutes,
        "last_run_at_utc": job.last_run_at.replace(tzinfo=timezone.utc).isoformat() if job.last_run_at else None,
    }


def execute_security_audit() -> dict[str, Any]:
    """Run a truthful local configuration audit, not a penetration test."""
    checks: list[dict[str, str]] = []

    secret = str(settings.secret_key or "")
    secret_ok = len(secret) >= 32 and secret not in {
        "CHANGE_THIS_SECRET_KEY",
        "CHANGE_ME_TO_A_LONG_RANDOM_SECRET",
    }
    checks.append({
        "id": "application_secret",
        "status": "PASS" if secret_ok else "FAIL",
        "detail": "JWT secret meets the configured minimum length." if secret_ok else "JWT secret is missing, default or too short.",
    })

    database_url = str(settings.database_url or "")
    db_ok = bool(database_url and not database_url.startswith("sqlite"))
    checks.append({
        "id": "database_configuration",
        "status": "PASS" if db_ok else "WARN",
        "detail": "A non-SQLite database URL is configured." if db_ok else "SQLite is configured; confirm this is intentional for the current runtime.",
    })

    cors = [item.strip() for item in str(settings.cors_origins or "").split(",") if item.strip()]
    cors_ok = bool(cors) and "*" not in cors
    checks.append({
        "id": "cors_origins",
        "status": "PASS" if cors_ok else "FAIL",
        "detail": "CORS uses explicit origins." if cors_ok else "CORS is empty or contains a wildcard origin.",
    })

    provider_configured = any((
        settings.gemini_api_key,
        settings.openrouter_api_key,
        settings.kimi_api_key,
    ))
    checks.append({
        "id": "ai_provider_fallback",
        "status": "PASS" if provider_configured else "WARN",
        "detail": "At least one AI provider credential is configured." if provider_configured else "No supported AI provider credential is configured.",
    })

    gmail_configured = bool(settings.gmail_client_id and settings.gmail_client_secret and settings.gmail_redirect_uri)
    checks.append({
        "id": "gmail_oauth",
        "status": "PASS" if gmail_configured else "WARN",
        "detail": "Gmail OAuth application settings are present." if gmail_configured else "Gmail OAuth application settings are incomplete.",
    })

    scheduler_ok = bool(settings.scheduler_enabled and not settings.serverless_mode)
    checks.append({
        "id": "background_scheduler",
        "status": "PASS" if scheduler_ok else "WARN",
        "detail": "The in-process scheduler is enabled." if scheduler_ok else "The in-process scheduler is disabled or the backend is running in serverless mode.",
    })

    tools = registry_summary()
    disconnected = [
        item["id"] for item in tools.get("tools", [])
        if item.get("status") in {"NOT_CONNECTED", "NOT_CONFIGURED", "NOT_INSTALLED"}
    ]
    checks.append({
        "id": "tool_connections",
        "status": "PASS" if not disconnected else "WARN",
        "detail": "All listed tools report a connected or available state." if not disconnected else "Tools requiring attention: " + ", ".join(disconnected[:12]),
    })

    passed = sum(item["status"] == "PASS" for item in checks)
    warnings = sum(item["status"] == "WARN" for item in checks)
    failed = sum(item["status"] == "FAIL" for item in checks)
    return {
        "status": "COMPLETED",
        "verified": True,
        "tool": "defensive_configuration_audit",
        "summary": {"passed": passed, "warnings": warnings, "failed": failed, "total": len(checks)},
        "checks": checks,
        "limitations": [
            "This checks MR AI configuration and declared connector readiness only.",
            "It does not perform external penetration testing, port scanning, malware scanning or a full dependency CVE audit.",
            "No credentials or secret values are included in the report.",
        ],
    }
