from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, update
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db
from .dependencies import get_current_user
from .models import ActivityLog, Notification, ScheduledJob, Task, User
from .schemas import ScheduleCreate, ScheduleUpdate
from .task_runner import run_pending_tasks
from .self_audit import maybe_run_self_audit

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

logger = logging.getLogger("mr_ai.scheduler")
POLL_SECONDS = 5
_scheduler_task: Optional[asyncio.Task] = None
_last_cycle_at: Optional[str] = None
_last_cycle_status = "NOT_RUN"
_last_cycle_error_type: Optional[str] = None
_last_cycle_summary: dict[str, int] = {
    "scheduled_jobs_triggered": 0,
    "tasks_processed": 0,
    "autopilot_users_checked": 0,
    "autopilot_users_due": 0,
    "new_jobs_found": 0,
    "application_drafts_ready": 0,
    "job_source_errors": 0,
    "approved_missions_processed": 0,
    "gmail_users_checked": 0,
    "gmail_messages_processed": 0,
    "gmail_drafts_created": 0,
    "gmail_replies_sent": 0,
    "gmail_followups_processed": 0,
    "gmail_assistant_errors": 0,
}


def scheduler_status() -> dict:
    """Expose non-sensitive worker health so hosted background execution is observable."""
    task = _scheduler_task
    return {
        "enabled_by_config": bool(settings.scheduler_enabled and not settings.serverless_mode),
        "loop_running": bool(task and not task.done()),
        "last_cycle_at": _last_cycle_at,
        "last_cycle_status": _last_cycle_status,
        "last_cycle_error_type": _last_cycle_error_type,
        "last_cycle_summary": dict(_last_cycle_summary),
        "truth_note": "Worker health does not prove a job application was submitted; task evidence is reported separately.",
    }


def _utcnow() -> datetime:
    return datetime.utcnow()


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _advance_next_run(job: ScheduledJob, now: datetime) -> None:
    if job.interval_minutes and job.interval_minutes > 0:
        next_run = job.next_run_at or now
        step = timedelta(minutes=job.interval_minutes)
        while next_run <= now:
            next_run += step
        job.next_run_at = next_run
        job.status = "ACTIVE"
    else:
        job.next_run_at = None
        job.status = "COMPLETED"


def _serialize(job: ScheduledJob) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "command": job.command,
        "status": job.status,
        "run_at": job.run_at.isoformat() if job.run_at else None,
        "interval_minutes": job.interval_minutes,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def run_due_jobs(db: Session, now: Optional[datetime] = None) -> int:
    now = now or _utcnow()
    due_jobs = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.status == "ACTIVE",
            ScheduledJob.next_run_at.isnot(None),
            ScheduledJob.next_run_at <= now,
        )
        .order_by(ScheduledJob.next_run_at.asc(), ScheduledJob.id.asc())
        .all()
    )

    fired = 0
    for job in due_jobs:
        db.add(
            Task(
                user_id=job.user_id,
                title=f"[SCHEDULED] {job.title}"[:255],
                description=job.command,
                status="PENDING",
                priority="NORMAL",
                agent="scheduler",
            )
        )
        db.add(
            Notification(
                user_id=job.user_id,
                title=job.title,
                message=f"Scheduled command queued: {job.command}",
                read=False,
            )
        )
        job.last_run_at = now
        _advance_next_run(job, now)
        db.add(
            ActivityLog(
                user_id=job.user_id,
                action="SCHEDULE_TRIGGERED",
                details=f"Schedule {job.id}: {job.title}",
            )
        )
        fired += 1

    if fired:
        db.commit()
    return fired


async def run_approved_pending_missions(db: Session, limit: int = 3) -> int:
    """Resume owner-approved orchestrator missions queued in the database."""
    from .orchestration.executor import execute_mission

    now = datetime.utcnow()
    stale_cutoff = now - timedelta(minutes=15)
    candidates = (
        db.query(Task)
        .filter(
            Task.agent == "orchestrator",
            Task.source == "orchestrator",
            Task.approved_by.is_not(None),
            Task.approved_by == Task.user_id,
            or_(
                Task.status == "PENDING",
                and_(Task.status.in_(["RUNNING", "IN_PROGRESS"]), Task.updated_at < stale_cutoff),
            ),
        )
        .order_by(Task.created_at.asc(), Task.id.asc())
        .limit(max(1, min(int(limit), 10)))
        .all()
    )
    processed = 0
    for candidate in candidates:
        expected_status = str(candidate.status or "").upper()
        conditions = [
            Task.id == candidate.id,
            Task.user_id == candidate.user_id,
            Task.agent == "orchestrator",
            Task.source == "orchestrator",
            Task.approved_by == candidate.user_id,
            Task.status == expected_status,
        ]
        if expected_status in {"RUNNING", "IN_PROGRESS"}:
            conditions.append(Task.updated_at < stale_cutoff)
        claim = db.execute(
            update(Task)
            .where(*conditions)
            .values(status="RUNNING", updated_at=now)
        )
        db.commit()
        if claim.rowcount != 1:
            continue
        mission = db.query(Task).filter(Task.id == candidate.id, Task.user_id == candidate.user_id).first()
        user = db.query(User).filter(User.id == candidate.user_id).first()
        if mission is None or user is None:
            if mission is not None:
                mission.status = "FAILED"
                mission.error = "Approved mission owner could not be loaded by the scheduler."
                db.commit()
            processed += 1
            continue
        try:
            await execute_mission(mission.description or mission.title, user, db, mission=mission)
        except Exception as exc:
            db.rollback()
            failed = db.query(Task).filter(Task.id == candidate.id, Task.user_id == candidate.user_id).first()
            if failed is not None:
                failed.status = "FAILED"
                failed.error = "Background mission execution failed: " + type(exc).__name__
                failed.updated_at = datetime.utcnow()
                db.add(ActivityLog(
                    user_id=candidate.user_id,
                    action="APPROVED_MISSION_FAILED",
                    details="task_id=" + str(candidate.id) + "; error_type=" + type(exc).__name__,
                ))
                db.commit()
            logger.error("Approved mission failed: task_id=%s error_type=%s", candidate.id, type(exc).__name__)
        processed += 1
    return processed


async def run_scheduler_cycle() -> tuple[int, int]:
    global _last_cycle_at, _last_cycle_status, _last_cycle_error_type, _last_cycle_summary
    db = SessionLocal()
    _last_cycle_at = datetime.now(timezone.utc).isoformat()
    _last_cycle_status = "RUNNING"
    _last_cycle_error_type = None
    summary = {
        "scheduled_jobs_triggered": 0,
        "tasks_processed": 0,
        "autopilot_users_checked": 0,
        "autopilot_users_due": 0,
        "new_jobs_found": 0,
        "application_drafts_ready": 0,
        "job_source_errors": 0,
        "approved_missions_processed": 0,
        "gmail_users_checked": 0,
        "gmail_messages_processed": 0,
        "gmail_drafts_created": 0,
        "gmail_replies_sent": 0,
        "gmail_followups_processed": 0,
        "gmail_assistant_errors": 0,
    }
    try:
        maybe_run_self_audit(db)
        fired = run_due_jobs(db)
        summary["scheduled_jobs_triggered"] = fired

        # Job Autopilot is user-scoped and interval-gated. It discovers new
        # public listings and prepares drafts while never claiming that a
        # form/email application was submitted.
        try:
            from .routers.jobs import run_job_autopilot_cycle
            autopilot_summary = await run_job_autopilot_cycle(db)
            summary["autopilot_users_checked"] = int(autopilot_summary.get("users_checked") or 0)
            summary["autopilot_users_due"] = int(autopilot_summary.get("users_due") or 0)
            summary["new_jobs_found"] = int(autopilot_summary.get("new_jobs") or 0)
            summary["application_drafts_ready"] = int(autopilot_summary.get("drafts_ready") or 0)
            summary["job_source_errors"] = int(autopilot_summary.get("errors") or 0)
        except Exception as exc:
            db.rollback()
            summary["job_source_errors"] += 1
            logger.error("Job Autopilot cycle failed: error_type=%s", type(exc).__name__)

        processed = await run_pending_tasks(db, limit=5)
        summary["tasks_processed"] = processed

        try:
            summary["approved_missions_processed"] = await run_approved_pending_missions(db, limit=3)
        except Exception as exc:
            db.rollback()
            logger.error("Approved mission dispatcher failed: error_type=%s", type(exc).__name__)

        try:
            from .gmail_assistant import run_gmail_assistant_cycle
            gmail_summary = await run_gmail_assistant_cycle(db)
            summary["gmail_users_checked"] = int(gmail_summary.get("users_checked") or 0)
            summary["gmail_messages_processed"] = int(gmail_summary.get("messages_processed") or 0)
            summary["gmail_drafts_created"] = int(gmail_summary.get("drafts_created") or 0)
            summary["gmail_replies_sent"] = int(gmail_summary.get("replies_sent") or 0)
            summary["gmail_followups_processed"] = int(gmail_summary.get("followups_processed") or 0)
            summary["gmail_assistant_errors"] = int(gmail_summary.get("errors") or 0)
        except Exception as exc:
            db.rollback()
            summary["gmail_assistant_errors"] += 1
            logger.error("Gmail VIP cycle failed: error_type=%s", type(exc).__name__)

        _last_cycle_summary = dict(summary)
        _last_cycle_status = "COMPLETED"
        if fired or processed or summary["autopilot_users_due"] or summary["approved_missions_processed"] or summary["gmail_messages_processed"] or summary["gmail_replies_sent"]:
            logger.info(
                "Scheduler cycle complete: triggered=%s processed=%s job_users=%s "
                "job_candidates=%s application_drafts=%s job_source_errors=%s",
                fired,
                processed,
                summary["autopilot_users_due"],
                summary["new_jobs_found"],
                summary["application_drafts_ready"],
                summary["job_source_errors"],
            )
        return fired, processed
    except Exception as exc:
        db.rollback()
        _last_cycle_status = "FAILED"
        _last_cycle_error_type = type(exc).__name__
        _last_cycle_summary = dict(summary)
        logger.exception("Scheduled job cycle failed")
        return 0, 0
    finally:
        db.close()


async def _scheduler_loop() -> None:
    while True:
        try:
            await run_scheduler_cycle()
        except asyncio.CancelledError:
            raise
        await asyncio.sleep(POLL_SECONDS)


def start_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("Scheduler Agent started")


async def stop_scheduler() -> None:
    global _scheduler_task
    task = _scheduler_task
    _scheduler_task = None
    if not task:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Scheduler Agent stopped")


@router.get("")
def list_schedules(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jobs = (
        db.query(ScheduledJob)
        .filter(ScheduledJob.user_id == current_user.id)
        .order_by(
            ScheduledJob.next_run_at.asc().nullslast(),
            ScheduledJob.id.desc(),
        )
        .all()
    )
    return [_serialize(job) for job in jobs]


@router.post("")
def create_schedule(
    data: ScheduleCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interval = data.interval_minutes
    if interval is not None and interval < 1:
        raise HTTPException(400, "interval_minutes must be at least 1")

    title = data.title.strip()[:255]
    command = data.command.strip()
    if not title or not command:
        raise HTTPException(400, "title and command are required")

    run_at = _as_utc_naive(data.run_at)
    job = ScheduledJob(
        user_id=current_user.id,
        title=title,
        command=command,
        status="ACTIVE",
        run_at=run_at,
        interval_minutes=interval,
        next_run_at=run_at,
    )
    db.add(job)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            action="SCHEDULE_CREATED",
            details=title,
        )
    )
    db.commit()
    db.refresh(job)
    return _serialize(job)


@router.patch("/{schedule_id}")
def update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.id == schedule_id,
            ScheduledJob.user_id == current_user.id,
        )
        .first()
    )
    if not job:
        raise HTTPException(404, "Schedule not found")

    updates = data.model_dump(exclude_unset=True)
    if "title" in updates:
        job.title = str(updates["title"]).strip()[:255]
    if "command" in updates:
        job.command = str(updates["command"]).strip()
    if "status" in updates:
        status = str(updates["status"]).strip().upper()
        if status not in {"ACTIVE", "PAUSED", "COMPLETED"}:
            raise HTTPException(400, "status must be ACTIVE, PAUSED or COMPLETED")
        job.status = status
    if "interval_minutes" in updates:
        interval = updates["interval_minutes"]
        if interval is not None and interval < 1:
            raise HTTPException(400, "interval_minutes must be at least 1")
        job.interval_minutes = interval
    if "run_at" in updates and updates["run_at"] is not None:
        job.run_at = _as_utc_naive(updates["run_at"])
        if job.status != "COMPLETED":
            job.next_run_at = job.run_at

    if not job.title or not job.command:
        raise HTTPException(400, "title and command cannot be empty")

    if job.status == "PAUSED":
        job.next_run_at = None
    elif job.status == "ACTIVE" and job.next_run_at is None:
        job.next_run_at = job.run_at

    db.add(
        ActivityLog(
            user_id=current_user.id,
            action="SCHEDULE_UPDATED",
            details=f"Schedule {job.id}",
        )
    )
    db.commit()
    db.refresh(job)
    return _serialize(job)


@router.post("/{schedule_id}/run-now")
def run_schedule_now(
    schedule_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.id == schedule_id,
            ScheduledJob.user_id == current_user.id,
        )
        .first()
    )
    if not job:
        raise HTTPException(404, "Schedule not found")

    job.status = "ACTIVE"
    job.next_run_at = _utcnow()
    db.add(
        ActivityLog(
            user_id=current_user.id,
            action="SCHEDULE_RUN_NOW",
            details=f"Schedule {job.id}",
        )
    )
    db.commit()
    db.refresh(job)
    return _serialize(job)


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.id == schedule_id,
            ScheduledJob.user_id == current_user.id,
        )
        .first()
    )
    if not job:
        raise HTTPException(404, "Schedule not found")

    db.delete(job)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            action="SCHEDULE_DELETED",
            details=f"Schedule {schedule_id}",
        )
    )
    db.commit()
    return {"deleted": True}
