from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog, ScheduledJob
from ..schemas import ScheduleCreate, ScheduleUpdate

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _validate_status(value: str) -> str:
    status = value.strip().upper()
    if status not in {"ACTIVE", "PAUSED", "COMPLETED"}:
        raise HTTPException(400, "status must be ACTIVE, PAUSED or COMPLETED")
    return status


def _validate_interval(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 1:
        raise HTTPException(400, "interval_minutes must be at least 1")
    return value


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


@router.get("")
def list_schedules(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jobs = (
        db.query(ScheduledJob)
        .filter(ScheduledJob.user_id == current_user.id)
        .order_by(ScheduledJob.next_run_at.asc().nullslast(), ScheduledJob.id.desc())
        .all()
    )
    return [_serialize(job) for job in jobs]


@router.post("")
def create_schedule(
    data: ScheduleCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interval = _validate_interval(data.interval_minutes)
    run_at = _as_utc_naive(data.run_at)

    job = ScheduledJob(
        user_id=current_user.id,
        title=data.title.strip()[:255],
        command=data.command.strip(),
        status="ACTIVE",
        run_at=run_at,
        interval_minutes=interval,
        next_run_at=run_at,
    )

    if not job.title or not job.command:
        raise HTTPException(400, "title and command are required")

    db.add(job)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            action="SCHEDULE_CREATED",
            details=job.title,
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
        job.status = _validate_status(str(updates["status"]))
    if "interval_minutes" in updates:
        job.interval_minutes = _validate_interval(updates["interval_minutes"])
    if "run_at" in updates:
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
