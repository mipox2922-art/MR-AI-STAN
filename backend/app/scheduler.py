from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal, get_db
from .dependencies import get_current_user
from .models import ActivityLog, Notification, ScheduledJob, Task
from .schemas import ScheduleCreate, ScheduleUpdate
from .task_runner import run_pending_tasks

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

logger = logging.getLogger("mr_ai.scheduler")
POLL_SECONDS = 5
_scheduler_task: Optional[asyncio.Task] = None


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


async def run_scheduler_cycle() -> tuple[int, int]:
    db = SessionLocal()
    try:
        fired = run_due_jobs(db)
        processed = await run_pending_tasks(db, limit=5)
        if fired or processed:
            logger.info(
                "Scheduler cycle complete: triggered=%s processed=%s",
                fired,
                processed,
            )
        return fired, processed
    except Exception:
        db.rollback()
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
