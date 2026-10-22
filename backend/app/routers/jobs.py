from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog, Notification, Setting, Task, TaskStep, User

router = APIRouter(prefix="/jobs", tags=["Job Research"])
logger = logging.getLogger("mr_ai.jobs")
TIMEOUT_SECONDS = 12.0


def _clean_job(item: dict[str, Any], source: str) -> dict[str, Any] | None:
    title = str(item.get("position") or item.get("title") or "").strip()
    company = str(item.get("company") or item.get("company_name") or "").strip()
    url = str(item.get("url") or item.get("job_url") or "").strip()
    if not title or not url or urlparse(url).scheme != "https":
        return None
    location = str(item.get("location") or item.get("candidate_required_location") or "Remote").strip()
    description = str(item.get("description") or item.get("description_text") or "").strip()
    tags = item.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return {
        "id": str(item.get("id") or url),
        "title": title[:255],
        "company": company[:180] or "Company not listed",
        "location": location[:180] or "Remote",
        "url": url,
        "description": description[:700],
        "tags": [str(tag)[:80] for tag in tags[:8]],
        "published_at": item.get("date") or item.get("publication_date") or item.get("created_at"),
        "source": source,
    }


async def _fetch_remoteok(client: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
    response = await client.get("https://remoteok.com/api", headers={"User-Agent": "MR-AI-STAN job research contact=owner"})
    response.raise_for_status()
    payload = response.json()
    rows = payload[1:] if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "legal" in payload[0] else payload
    words = [word.casefold() for word in query.split() if len(word) > 1]
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        job = _clean_job(row, "RemoteOK")
        if not job:
            continue
        searchable = " ".join([job["title"], job["company"], job["location"], job["description"], *job["tags"]]).casefold()
        if not words or any(word in searchable for word in words):
            result.append(job)
    return result


async def _fetch_remotive(client: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
    response = await client.get("https://remotive.com/api/remote-jobs", params={"search": query, "limit": 50})
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("jobs", []) if isinstance(payload, dict) else []
    return [job for row in rows if isinstance(row, dict) if (job := _clean_job(row, "Remotive"))]


async def research_public_jobs(query: str, limit: int = 25) -> dict[str, Any]:
    query = query.strip()[:180]
    if len(query) < 2:
        raise HTTPException(400, "Enter at least two characters to research jobs.")
    limit = max(1, min(limit, 50))
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        results = await asyncio.gather(
            _fetch_remoteok(client, query),
            _fetch_remotive(client, query),
            return_exceptions=True,
        )

    jobs: list[dict[str, Any]] = []
    errors: list[str] = []
    for source_result in results:
        if isinstance(source_result, Exception):
            errors.append(type(source_result).__name__)
            logger.warning("Job source unavailable: %s", type(source_result).__name__)
            continue
        jobs.extend(source_result)

    deduplicated: dict[str, dict[str, Any]] = {}
    for job in jobs:
        deduplicated.setdefault(job["url"].rstrip("/").casefold(), job)
    ordered = sorted(
        deduplicated.values(),
        key=lambda job: str(job.get("published_at") or ""),
        reverse=True,
    )[:limit]
    if not ordered and len(errors) == 2:
        raise HTTPException(502, "Job sources are temporarily unavailable. Try again later.")

    return {
        "status": "COMPLETED" if ordered else "NO_RESULTS",
        "query": query,
        "count": len(ordered),
        "results": ordered,
        "sources": ["RemoteOK", "Remotive"],
        "source_warnings": errors,
        "note": "Public remote-job feeds; results must be checked on the employer's site. MR AI does not submit applications automatically.",
    }


@router.get("/research")
async def research_jobs(
    query: str,
    limit: int = 25,
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    return await research_public_jobs(query, limit)


AUTOPILOT_CONFIG_KEY = "job_autopilot_config"
APPLICATION_PROFILE_KEY = "job_application_profile"
DEFAULT_AUTOPILOT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "queries": ["graphic designer", "AI data annotation", "virtual assistant", "remote customer support"],
    "interval_hours": 6,
    "max_new_jobs": 12,
    "last_run_at": None,
}


def _setting_row(db: Session, user_id: int, key: str) -> Setting | None:
    return (
        db.query(Setting)
        .filter(Setting.user_id == user_id, Setting.key == key)
        .order_by(Setting.id.desc())
        .first()
    )


def _read_json_setting(db: Session, user_id: int, key: str, default: dict[str, Any]) -> dict[str, Any]:
    row = _setting_row(db, user_id, key)
    if not row or not row.value:
        return dict(default)
    try:
        value = json.loads(row.value)
    except (TypeError, ValueError):
        return dict(default)
    return value if isinstance(value, dict) else dict(default)


def _write_json_setting(db: Session, user_id: int, key: str, value: dict[str, Any]) -> None:
    row = _setting_row(db, user_id, key)
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if row:
        row.value = encoded
    else:
        db.add(Setting(user_id=user_id, key=key, value=encoded))


def _profile_ready(profile: dict[str, Any]) -> bool:
    return bool(
        str(profile.get("full_name") or "").strip()
        and str(profile.get("email") or "").strip()
        and (
            profile.get("skills")
            or str(profile.get("experience_summary") or "").strip()
        )
    )


def _build_application_draft(job: dict[str, Any], profile: dict[str, Any]) -> dict[str, str] | None:
    if not _profile_ready(profile):
        return None
    name = str(profile.get("full_name") or "").strip()[:120]
    company = str(job.get("company") or "the hiring team").strip()[:160]
    title = str(job.get("title") or "the advertised role").strip()[:180]
    skills = profile.get("skills") or []
    if isinstance(skills, str):
        skills = [part.strip() for part in skills.split(",") if part.strip()]
    skills_text = ", ".join(str(item).strip() for item in skills[:12] if str(item).strip())
    summary = str(profile.get("experience_summary") or "").strip()[:1500]
    portfolio = str(profile.get("portfolio_url") or "").strip()
    paragraphs = [
        f"Dear {company} Hiring Team,",
        f"I am applying for the {title} position. My relevant skills include {skills_text}."
        if skills_text else f"I am applying for the {title} position.",
    ]
    if summary:
        paragraphs.append(summary)
    paragraphs.append(
        "I would welcome the opportunity to discuss how my actual skills and experience can support your team. "
        "I can provide further details or work samples on request."
    )
    if portfolio:
        paragraphs.append(f"Portfolio or work samples: {portfolio}")
    paragraphs.append(f"Kind regards,\n{name}")
    return {
        "subject": f"Application for {title}",
        "cover_letter": "\n\n".join(paragraphs),
        "source_note": "Draft generated only from the candidate information saved in MR AI. Review it before sending; no application was submitted.",
    }


def _refresh_waiting_application_drafts(
    db: Session,
    user_id: int,
    profile: dict[str, Any],
) -> int:
    """Resume application drafts as soon as the candidate profile is completed."""
    if not _profile_ready(profile):
        return 0
    refreshed = 0
    rows = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.agent == "jobs",
            Task.source == "autopilot",
            Task.status == "WAITING_FOR_PROFILE",
        )
        .order_by(Task.id.asc())
        .all()
    )
    for task in rows:
        try:
            packet = json.loads(task.result or "{}")
        except (TypeError, ValueError):
            continue
        job = packet.get("job") if isinstance(packet, dict) else None
        if not isinstance(job, dict):
            continue
        draft = _build_application_draft(job, profile)
        if not draft:
            continue
        packet["application_draft"] = draft
        packet["status"] = "READY_FOR_REVIEW"
        packet["match_score"] = _match_score(job, profile)
        packet["updated_at"] = datetime.now(timezone.utc).isoformat()
        task.result = json.dumps(packet, ensure_ascii=False, default=str)
        task.status = "READY_FOR_REVIEW"
        task.progress = 50
        task.error = "Draft prepared. Automatic submission is unavailable; review before sending."
        step = (
            db.query(TaskStep)
            .filter(TaskStep.task_id == task.id, TaskStep.position == 2)
            .first()
        )
        if step:
            step.title = "Andaa barua ya maombi kutoka taarifa za profile"
            step.state = "pending"
            step.evidence = json.dumps({
                "draft_ready": True,
                "submitted": False,
                "blocker": "NO_CONNECTED_SUBMISSION_HAND",
            }, ensure_ascii=False)
        refreshed += 1
    return refreshed


def _job_url_from_task(task: Task) -> str | None:
    match = re.search(r"^Job URL:\s*(https://\S+)", str(task.description or ""), flags=re.MULTILINE)
    if match:
        return match.group(1).rstrip(".,)/")
    try:
        result = json.loads(task.result or "{}")
    except (TypeError, ValueError):
        result = {}
    job = result.get("job") if isinstance(result, dict) else {}
    url = str((job or {}).get("url") or "").strip() if isinstance(job, dict) else ""
    return url if url.startswith("https://") else None


def _match_score(job: dict[str, Any], profile: dict[str, Any]) -> int | None:
    skills = profile.get("skills") or []
    if isinstance(skills, str):
        skills = [part.strip() for part in skills.split(",") if part.strip()]
    if not skills:
        return None
    text = " ".join([
        str(job.get("title") or ""),
        str(job.get("description") or ""),
        str(job.get("company") or ""),
        " ".join(str(item) for item in (job.get("tags") or [])),
    ]).casefold()
    terms = {str(item).strip().casefold() for item in skills if str(item).strip()}
    matched = sum(1 for term in terms if term and term in text)
    return min(100, round(100 * matched / max(1, min(5, len(terms)))))


async def run_job_autopilot_for_user(
    db: Session,
    user_id: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Find new public job listings and prepare honest application drafts in the background."""
    config = _read_json_setting(db, user_id, AUTOPILOT_CONFIG_KEY, DEFAULT_AUTOPILOT_CONFIG)
    profile = _read_json_setting(db, user_id, APPLICATION_PROFILE_KEY, {})
    refreshed_before_search = _refresh_waiting_application_drafts(db, user_id, profile)
    if refreshed_before_search:
        db.commit()
    if not config.get("enabled", True) and not force:
        return {"status": "DISABLED", "user_id": user_id, "new_jobs": 0, "drafts_ready": 0}

    interval_hours = max(1, min(168, int(config.get("interval_hours") or 6)))
    now = datetime.now(timezone.utc)
    last_run = None
    try:
        last_value = config.get("last_run_at")
        if last_value:
            last_run = datetime.fromisoformat(str(last_value).replace("Z", "+00:00"))
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        last_run = None
    if not force and last_run and now - last_run < timedelta(hours=interval_hours):
        return {
            "status": "NOT_DUE",
            "user_id": user_id,
            "new_jobs": 0,
            "drafts_ready": 0,
            "next_run_at": (last_run + timedelta(hours=interval_hours)).isoformat(),
        }

    queries = config.get("queries") or DEFAULT_AUTOPILOT_CONFIG["queries"]
    if isinstance(queries, str):
        queries = [item.strip() for item in queries.split(",") if item.strip()]
    queries = list(dict.fromkeys(str(item).strip()[:100] for item in queries if str(item).strip()))[:8]
    if not queries:
        queries = list(DEFAULT_AUTOPILOT_CONFIG["queries"])
    max_new_jobs = max(1, min(30, int(config.get("max_new_jobs") or 12)))

    # Reserve the run before making network calls so simultaneous scheduler
    # cycles don't duplicate the same set of searches.
    config["last_run_at"] = now.isoformat()
    config["enabled"] = bool(config.get("enabled", True))
    _write_json_setting(db, user_id, AUTOPILOT_CONFIG_KEY, config)
    db.commit()

    responses = await asyncio.gather(
        *(research_public_jobs(query, limit=25) for query in queries),
        return_exceptions=True,
    )
    candidates: dict[str, dict[str, Any]] = {}
    source_errors: list[str] = []
    for response in responses:
        if isinstance(response, Exception):
            source_errors.append(type(response).__name__)
            continue
        for job in response.get("results") or []:
            if not isinstance(job, dict):
                continue
            url = str(job.get("url") or "").strip().rstrip("/")
            if url.startswith("https://"):
                candidates.setdefault(url.casefold(), job)

    existing_tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.agent == "jobs")
        .order_by(Task.id.desc())
        .all()
    )
    existing_by_url = {
        url.casefold(): task
        for task in existing_tasks
        if (url := _job_url_from_task(task))
    }
    new_jobs = 0
    drafts_ready = 0
    waiting_for_profile = 0
    ready_to_review = 0
    profile_ready = _profile_ready(profile)

    for url_key, job in sorted(candidates.items(), key=lambda item: str(item[1].get("published_at") or ""), reverse=True):
        task = existing_by_url.get(url_key)
        if task is not None:
            # If the owner has since saved a profile, resume drafts that were
            # waiting for it instead of creating duplicate applications.
            if task.status == "WAITING_FOR_PROFILE" and profile_ready:
                refreshed_now = _refresh_waiting_application_drafts(db, user_id, profile)
                if refreshed_now:
                    drafts_ready += refreshed_now
                    ready_to_review += refreshed_now
            continue

        job["url"] = str(job.get("url") or "").strip()
        draft = _build_application_draft(job, profile)
        task_status = "READY_FOR_REVIEW" if draft else "WAITING_FOR_PROFILE"
        job_payload = {
            "workflow": "JOB_APPLICATION",
            "status": task_status,
            "job": job,
            "match_score": _match_score(job, profile),
            "application_draft": draft,
            "submission": {
                "status": "NOT_SUBMITTED",
                "reason": "No verified form-submission hand is connected to this hosted runtime.",
            },
            "updated_at": now.isoformat(),
        }
        title = str(job.get("title") or "Nafasi ya kazi").strip()[:180]
        company = str(job.get("company") or "Company not listed").strip()[:140]
        url = str(job.get("url") or "")
        location = str(job.get("location") or "Remote").strip()[:120]
        desc = str(job.get("description") or "").strip()[:700]
        task = Task(
            user_id=user_id,
            title=f"Application prep: {title} · {company}"[:255],
            description=(
                f"Company: {company}\nRole: {title}\nLocation: {location}\n"
                f"Job URL: {url}\nSource: {job.get('source') or 'public job feed'}\n\n{desc}"
            )[:12000],
            status=task_status,
            priority="NORMAL",
            agent="jobs",
            source="autopilot",
            requested_by="MR AI Job Autopilot",
            progress=50,
            result=json.dumps(job_payload, ensure_ascii=False, default=str),
            error=(
                "Candidate profile is incomplete. Add name, email, skills and/or experience summary to prepare an application draft."
                if not draft else
                "Draft prepared; a connected and verified application-submission hand is not available."
            ),
        )
        db.add(task)
        db.flush()
        db.add(TaskStep(
            task_id=task.id,
            position=1,
            title="Nafasi imepatikana kwenye public job feed",
            state="verified",
            evidence=json.dumps({
                "source": job.get("source"),
                "url": url,
                "title": title,
                "found_at": now.isoformat(),
            }, ensure_ascii=False),
            verified_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        db.add(TaskStep(
            task_id=task.id,
            position=2,
            title="Andaa barua ya maombi na profile",
            state="pending",
            evidence=json.dumps({
                "draft_ready": bool(draft),
                "submitted": False,
                "blocker": None if draft else "APPLICATION_PROFILE_INCOMPLETE",
            }, ensure_ascii=False),
        ))
        existing_by_url[url_key] = task
        new_jobs += 1
        if draft:
            drafts_ready += 1
            ready_to_review += 1
        else:
            waiting_for_profile += 1
        if new_jobs >= max_new_jobs:
            break

    db.add(ActivityLog(
        user_id=user_id,
        action="JOB_AUTOPILOT_CYCLE",
        details=(
            f"queries={len(queries)}; candidates={len(candidates)}; new={new_jobs}; "
            f"drafts={drafts_ready}; waiting_profile={waiting_for_profile}; source_errors={len(source_errors)}"
        ),
    ))
    if new_jobs:
        db.add(Notification(
            user_id=user_id,
            title="MR AI Job Autopilot report",
            message=(
                f"Utafutaji wa ajira umekamilika: nafasi mpya {new_jobs}, "
                f"drafts zilizoandaliwa {drafts_ready}, zinasubiri profile {waiting_for_profile}. "
                "Hakuna ombi lililotumwa kiotomatiki."
            ),
            read=False,
        ))
    db.commit()
    return {
        "status": "COMPLETED" if not source_errors or candidates else "SOURCE_ERROR",
        "user_id": user_id,
        "queries": queries,
        "candidate_count": len(candidates),
        "new_jobs": new_jobs,
        "drafts_ready": drafts_ready,
        "waiting_for_profile": waiting_for_profile,
        "ready_to_review": ready_to_review,
        "applications_submitted": 0,
        "source_errors": source_errors,
        "profile_ready": profile_ready,
        "auto_submit_available": False,
        "last_run_at": config["last_run_at"],
    }


async def run_job_autopilot_cycle(db: Session) -> dict[str, int]:
    """Run due, user-scoped job research for every account enabled in settings."""
    counts = {"users_checked": 0, "users_due": 0, "new_jobs": 0, "drafts_ready": 0, "errors": 0}
    users = db.query(User).order_by(User.id.asc()).all()
    for user in users:
        config_row = _setting_row(db, user.id, AUTOPILOT_CONFIG_KEY)
        if config_row is None:
            _write_json_setting(db, user.id, AUTOPILOT_CONFIG_KEY, dict(DEFAULT_AUTOPILOT_CONFIG))
            db.commit()
        config = _read_json_setting(db, user.id, AUTOPILOT_CONFIG_KEY, DEFAULT_AUTOPILOT_CONFIG)
        counts["users_checked"] += 1
        if not config.get("enabled", True):
            continue
        result = await run_job_autopilot_for_user(db, user.id, force=False)
        if result.get("status") != "NOT_DUE":
            counts["users_due"] += 1
            counts["new_jobs"] += int(result.get("new_jobs") or 0)
            counts["drafts_ready"] += int(result.get("drafts_ready") or 0)
            counts["errors"] += len(result.get("source_errors") or [])
    return counts


@router.get("/autopilot")
def get_job_autopilot_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    config = _read_json_setting(db, current_user.id, AUTOPILOT_CONFIG_KEY, DEFAULT_AUTOPILOT_CONFIG)
    profile = _read_json_setting(db, current_user.id, APPLICATION_PROFILE_KEY, {})
    rows = (
        db.query(Task)
        .filter(Task.user_id == current_user.id, Task.source == "autopilot", Task.agent == "jobs")
        .all()
    )
    return {
        "config": config,
        "profile": profile,
        "profile_ready": _profile_ready(profile),
        "auto_submit_available": False,
        "submission_blocker": "Hosted job-feed search and draft preparation are available; actual submission requires a connected, verified form/email execution hand, which is not wired in this release.",
        "metrics": {
            "jobs_found": len(rows),
            "drafts_ready": sum(1 for task in rows if task.status == "READY_FOR_REVIEW"),
            "waiting_for_profile": sum(1 for task in rows if task.status == "WAITING_FOR_PROFILE"),
            "applications_submitted_automatically": 0,
            "failed": sum(1 for task in rows if task.status in {"FAILED", "ERROR"}),
        },
    }


@router.put("/autopilot")
def update_job_autopilot_config(
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    config = _read_json_setting(db, current_user.id, AUTOPILOT_CONFIG_KEY, DEFAULT_AUTOPILOT_CONFIG)
    if "enabled" in payload:
        config["enabled"] = payload["enabled"] is True
    if "queries" in payload:
        values = payload["queries"]
        if isinstance(values, str):
            values = [part.strip() for part in values.splitlines() if part.strip()]
        if not isinstance(values, list):
            raise HTTPException(400, "queries must be a list of role searches.")
        queries = list(dict.fromkeys(str(value).strip()[:100] for value in values if str(value).strip()))[:8]
        if not queries:
            raise HTTPException(400, "Add at least one job-search role.")
        config["queries"] = queries
    if "interval_hours" in payload:
        try:
            config["interval_hours"] = max(1, min(168, int(payload["interval_hours"])))
        except (ValueError, TypeError):
            raise HTTPException(400, "interval_hours must be an integer from 1 to 168.")
    if "max_new_jobs" in payload:
        try:
            config["max_new_jobs"] = max(1, min(30, int(payload["max_new_jobs"])))
        except (ValueError, TypeError):
            raise HTTPException(400, "max_new_jobs must be an integer from 1 to 30.")
    _write_json_setting(db, current_user.id, AUTOPILOT_CONFIG_KEY, config)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="JOB_AUTOPILOT_CONFIG_UPDATED",
        details=f"enabled={config.get('enabled')}; queries={len(config.get('queries') or [])}; interval_hours={config.get('interval_hours')}",
    ))
    db.commit()
    return {"status": "SAVED", "config": config}


@router.put("/autopilot/profile")
def update_job_application_profile(
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    existing = _read_json_setting(db, current_user.id, APPLICATION_PROFILE_KEY, {})
    allowed = {"full_name", "email", "phone", "location", "skills", "experience_summary", "portfolio_url", "resume_text"}
    profile = {key: existing.get(key, "") for key in allowed}
    for key in allowed & payload.keys():
        value = payload[key]
        if key == "skills" and isinstance(value, list):
            profile[key] = [str(item).strip()[:100] for item in value if str(item).strip()][:20]
        else:
            profile[key] = str(value or "").strip()[:6000 if key == "resume_text" else 1800]
    if profile.get("email") and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", profile["email"]):
        raise HTTPException(400, "Enter a valid email address.")
    if profile.get("portfolio_url") and urlparse(profile["portfolio_url"]).scheme != "https":
        raise HTTPException(400, "Portfolio URL must use HTTPS.")
    _write_json_setting(db, current_user.id, APPLICATION_PROFILE_KEY, profile)
    refreshed_drafts = _refresh_waiting_application_drafts(db, current_user.id, profile)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="JOB_APPLICATION_PROFILE_UPDATED",
        details=f"profile_ready={_profile_ready(profile)}; resume_text_present={bool(profile.get('resume_text'))}",
    ))
    db.commit()
    return {
        "status": "SAVED",
        "profile_ready": _profile_ready(profile),
        "drafts_refreshed": refreshed_drafts,
        "message": (
            "Profile saved. New runs can prepare application drafts from the supplied facts."
            if _profile_ready(profile) else
            "Profile saved, but add full name, email and skills or an experience summary before drafts can be prepared."
        ),
    }


@router.post("/autopilot/run-now")
async def run_job_autopilot_now(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    config = _read_json_setting(db, current_user.id, AUTOPILOT_CONFIG_KEY, DEFAULT_AUTOPILOT_CONFIG)
    config["enabled"] = True
    config["last_run_at"] = None
    _write_json_setting(db, current_user.id, AUTOPILOT_CONFIG_KEY, config)
    db.commit()
    return await run_job_autopilot_for_user(db, current_user.id, force=True)


@router.post("/save")
def save_job(
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()[:255]
    company = str(payload.get("company") or "Company not listed").strip()[:180]
    url = str(payload.get("url") or "").strip()
    description = str(payload.get("description") or "").strip()[:3000]
    if not title or not url or urlparse(url).scheme != "https":
        raise HTTPException(400, "A job title and valid HTTPS job URL are required.")

    task = Task(
        user_id=current_user.id,
        title=f"Job application: {title}"[:255],
        description=f"Company: {company}\nJob URL: {url}\n\n{description}",
        status="PENDING",
        priority="NORMAL",
        agent="jobs",
        source="boss",
        requested_by=str(getattr(current_user, "username", None) or "Boss Ferisi"),
        progress=0,
    )
    db.add(task)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="JOB_SAVED",
        details=f"{title} at {company} | {url}"[:500],
    ))
    db.commit()
    db.refresh(task)
    return {
        "status": "SAVED",
        "task": {"id": task.id, "title": task.title, "status": task.status, "agent": task.agent},
    }


def _build_tracking_record(
    status: str,
    evidence_url: str | None,
    previous: dict[str, Any],
    owner_confirmed: bool,
) -> dict[str, Any]:
    # None means the caller omitted the field; an empty string means clear it.
    stored_evidence_url = (
        str(previous.get("evidence_url") or "").strip()
        if evidence_url is None
        else evidence_url.strip()
    )
    return {
        "status": status,
        "evidence_url": stored_evidence_url or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        # Neither a user-supplied URL nor owner confirmation is independent verification.
        "verified": False,
        "owner_confirmed": owner_confirmed,
        "evidence_status": "PROVIDED_NOT_CHECKED" if stored_evidence_url else "NOT_PROVIDED",
        "verification_method": (
            "evidence_link_provided_not_checked" if stored_evidence_url
            else "owner_confirmation" if owner_confirmed
            else "unconfirmed"
        ),
        "truth_note": "Status is user-reported; external evidence has not been independently checked.",
    }


@router.patch("/{task_id}/tracking")
def update_job_tracking(
    task_id: int,
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist application tracking separately from task execution status."""
    allowed = {"SAVED", "APPLIED", "RESPONSE_RECEIVED", "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN"}
    status = str(payload.get("status") or "").strip().upper()
    if status not in allowed:
        raise HTTPException(400, f"Status must be one of: {', '.join(sorted(allowed))}.")
    evidence_url = (
        str(payload.get("evidence_url") or "").strip()
        if "evidence_url" in payload
        else None
    )
    if evidence_url and urlparse(evidence_url).scheme != "https":
        raise HTTPException(400, "Evidence URL must use HTTPS.")
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.user_id == current_user.id, Task.agent == "jobs")
        .first()
    )
    if not task:
        raise HTTPException(404, "Saved job task not found.")
    previous: dict[str, Any] = {}
    try:
        decoded = json.loads(task.result or "{}")
        if isinstance(decoded, dict):
            previous = decoded
    except (TypeError, ValueError):
        previous = {}
    owner_confirmed = payload.get("owner_confirmed") is True
    tracking = _build_tracking_record(status, evidence_url, previous, owner_confirmed)
    # Preserve the autopilot's source/job/draft packet when recording a
    # user-reported application status. Tracking is not independent proof of
    # submission, so only the explicit tracking fields are updated.
    if previous.get("workflow") == "JOB_APPLICATION":
        merged_result = {**previous, "tracking": tracking}
    else:
        merged_result = {**previous, **tracking}
    task.result = json.dumps(merged_result, ensure_ascii=False, default=str)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="JOB_TRACKING_UPDATED",
        details=f"Task {task.id}: {status}; verification={tracking['verification_method']}"[:500],
    ))
    db.commit()
    db.refresh(task)
    return {"status": "UPDATED", "task_id": task.id, "tracking": tracking}
