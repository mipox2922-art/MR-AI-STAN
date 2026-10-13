from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog, Task

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
    evidence_url = str(payload.get("evidence_url") or "").strip()
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
    tracking = {
        "status": status,
        "evidence_url": evidence_url or previous.get("evidence_url"),
        "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "verified": status != "SAVED" and bool(evidence_url or payload.get("owner_confirmed") is True),
        "verification_method": "evidence_url" if evidence_url else "owner_confirmed" if payload.get("owner_confirmed") is True else "unverified",
    }
    task.result = json.dumps(tracking)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="JOB_TRACKING_UPDATED",
        details=f"Task {task.id}: {status}; verification={tracking['verification_method']}"[:500],
    ))
    db.commit()
    db.refresh(task)
    return {"status": "UPDATED", "task_id": task.id, "tracking": tracking}
