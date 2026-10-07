from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import ActivityLog, Notification, ScheduledJob, Task

logger = logging.getLogger("mr_ai.scheduler")

POLL_SECONDS = 5
_scheduler_task: Optional[asyncio.Task] = None


def _utcnow() -> datetime:
    return datetime.utcnow()


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
        # A schedule creates a durable Task rather than executing arbitrary
        # commands. The task can then pass through MR AI's normal permissioned
        # orchestration path.
        task = Task(
            user_id=job.user_id,
            title=f"[SCHEDULED] {job.title}"[:255],
            description=job.command,
            status="PENDING",
            priority="NORMAL",
            agent="scheduler",
        )
        db.add(task)

        notification = Notification(
            user_id=job.user_id,
            title=job.title,
            message=f"Scheduled command queued: {job.command}",
            read=False,
        )
        db.add(notification)

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


async def _scheduler_loop() -> None:
    while True:
        db = SessionLocal()
        try:
            run_due_jobs(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            db.rollback()
            logger.exception("Scheduled job cycle failed")
        finally:
            db.close()

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
