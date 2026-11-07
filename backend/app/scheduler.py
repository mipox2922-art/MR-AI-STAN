from __future__ import annotations

import json
import re
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
from .models import ActivityLog, Notification, ScheduledJob, Setting, Task, TaskStep, User
from .schemas import ScheduleCreate, ScheduleUpdate
from .task_runner import run_pending_tasks
from .self_audit import maybe_run_self_audit

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

logger = logging.getLogger("mr_ai.scheduler")
POLL_SECONDS = 5
_scheduler_task: Optional[asyncio.Task] = None
# The in-process poller and GitHub OIDC wake-up share this process and cycle.
# Serialize them so they cannot claim the same pending task concurrently.
_scheduler_cycle_lock = asyncio.Lock()
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
    "chief_of_staff_users_checked": 0,
    "chief_of_staff_missions_started": 0,
    "chief_of_staff_missions_resumed": 0,
    "chief_of_staff_missions_completed": 0,
    "chief_of_staff_missions_waiting": 0,
    "chief_of_staff_missions_pending": 0,
    "chief_of_staff_missions_waiting_for_hand": 0,
    "chief_of_staff_missions_waiting_for_approval": 0,
    "chief_of_staff_missions_waiting_for_verification": 0,
    "chief_of_staff_missions_failed": 0,
    "chief_of_staff_missions_other_waiting": 0,
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
                agent="orchestrator",
                source="orchestrator",
                requested_by=f"schedule:{job.id}"[:100],
                approved_by=job.user_id,
                approved_at=now,
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


async def run_pending_coding_verifications(db: Session, limit: int = 5) -> int:
    """Poll Coding Agent PR checks and reconcile the parent mission when CI finishes."""
    from .connectors.coding_workspace import CodingWorkspaceError, get_commit_checks

    rows = (
        db.query(Task)
        .filter(
            Task.agent == "coding",
            Task.source == "coding_agent",
            Task.status == "IN_PROGRESS",
        )
        .order_by(Task.created_at.asc(), Task.id.asc())
        .limit(max(1, min(int(limit), 20)))
        .all()
    )
    processed = 0
    for task in rows:
        try:
            result = json.loads(task.result or "{}")
            if not isinstance(result, dict):
                continue
            commit_sha = str(result.get("commit_sha") or "").strip()
            if not commit_sha:
                continue
            checks = await get_commit_checks(commit_sha)
            ci_status = str(checks.get("status") or "RUNNING").upper()
            if ci_status not in {"PASSED", "FAILED"}:
                continue

            now = datetime.utcnow()
            verified = ci_status == "PASSED"
            task.status = "COMPLETED" if verified else "FAILED"
            task.progress = 100 if verified else 25
            task.error = None if verified else "GitHub Actions checks failed for the Coding Agent commit."
            result["ci"] = ci_status
            result["checks"] = checks
            result["verified_at"] = now.replace(tzinfo=timezone.utc).isoformat()
            task.result = json.dumps(result, ensure_ascii=False, default=str)

            child_step = (
                db.query(TaskStep)
                .filter(TaskStep.task_id == task.id)
                .order_by(TaskStep.position.asc())
                .first()
            )
            if child_step is None:
                child_step = TaskStep(
                    task_id=task.id,
                    position=1,
                    title="Verify GitHub Actions for the isolated patch PR",
                )
                db.add(child_step)
            child_step.state = "verified" if verified else "failed"
            child_step.verified_at = now if verified else None
            child_step.evidence = json.dumps({
                "commit_sha": commit_sha,
                "branch": result.get("branch"),
                "pull_request": (result.get("pull_request") or {}).get("url"),
                "ci_status": ci_status,
                "checks": checks.get("checks") or [],
                "verified": verified,
            }, ensure_ascii=False, default=str)

            requested_by = str(task.requested_by or "")
            match = re.fullmatch(r"mission:(\d+):(\d+)", requested_by)
            if match:
                mission_id = int(match.group(1))
                position = int(match.group(2))
                parent = db.query(Task).filter(
                    Task.id == mission_id,
                    Task.user_id == task.user_id,
                    Task.agent == "orchestrator",
                    Task.source == "orchestrator",
                ).first()
                if parent is not None:
                    try:
                        parent_result = json.loads(parent.result or "{}")
                    except (TypeError, ValueError):
                        parent_result = {}
                    if not isinstance(parent_result, dict):
                        parent_result = {}
                    mission_steps = parent_result.get("steps") or []
                    updated_step = next(
                        (item for item in mission_steps if int(item.get("step") or 0) == position),
                        None,
                    )
                    if updated_step is not None:
                        updated_step["status"] = "COMPLETED" if verified else "FAILED"
                        updated_step["verified"] = verified
                        updated_step["evidence"] = {
                            **(updated_step.get("evidence") or {}),
                            "message": (
                                "GitHub Actions imekamilika: checks zote zimepita."
                                if verified else
                                "GitHub Actions imeripoti failure; patch haijathibitishwa."
                            ),
                            "ci_status": ci_status,
                            "checks": checks.get("checks") or [],
                            "commit_sha": commit_sha,
                            "pull_request": (result.get("pull_request") or {}).get("url"),
                            "coding_task_id": task.id,
                        }
                        parent_step = db.query(TaskStep).filter(
                            TaskStep.task_id == parent.id,
                            TaskStep.position == position,
                        ).first()
                        if parent_step is not None:
                            parent_step.state = "verified" if verified else "failed"
                            parent_step.verified_at = now if verified else None
                            parent_step.evidence = json.dumps({
                                "task_id": parent.id,
                                "agent": "coding",
                                "tool": "coding_agent",
                                "execution_status": updated_step["status"],
                                "verified": verified,
                                "output": updated_step["evidence"],
                                "step_result": updated_step,
                            }, ensure_ascii=False, default=str)

                    parent_rows = db.query(TaskStep).filter(TaskStep.task_id == parent.id).all()
                    verified_count = sum(
                        str(row.state or "").lower() == "verified" and bool(str(row.evidence or "").strip())
                        for row in parent_rows
                    )
                    failed_parent = any(str(row.state or "").lower() == "failed" for row in parent_rows)
                    all_verified = bool(parent_rows) and verified_count == len(parent_rows)
                    waiting_for_hand = False
                    for row in parent_rows:
                        try:
                            step_evidence = json.loads(row.evidence or "{}")
                        except (TypeError, ValueError):
                            step_evidence = {}
                        execution_status = str(step_evidence.get("execution_status") or "").upper()
                        if execution_status in {"WAITING_FOR_HAND", "NOT_CONNECTED", "WAITING_APPROVAL"}:
                            waiting_for_hand = True
                            break
                    parent.progress = int(verified_count / len(parent_rows) * 100) if parent_rows else 0
                    if failed_parent:
                        parent.status = "FAILED"
                        parent.error = "A Coding Agent step failed GitHub Actions verification."
                    elif all_verified:
                        parent.status = "COMPLETED"
                        parent.error = None
                    elif waiting_for_hand:
                        parent.status = "WAITING_FOR_HAND"
                    else:
                        parent.status = "WAITING_FOR_VERIFICATION"
                    parent_result["status"] = parent.status
                    parent_result["steps"] = mission_steps
                    parent_result["verified_steps"] = verified_count
                    parent_result["total_steps"] = len(parent_rows)
                    parent.result = json.dumps(parent_result, ensure_ascii=False, default=str)
                    db.add(ActivityLog(
                        user_id=parent.user_id,
                        action="MISSION_CODING_CI_VERIFIED" if verified else "MISSION_CODING_CI_FAILED",
                        details=f"mission_id={parent.id}; coding_task_id={task.id}; commit={commit_sha}; ci={ci_status}",
                    ))

            db.add(ActivityLog(
                user_id=task.user_id,
                action="CODING_AGENT_CI_VERIFIED" if verified else "CODING_AGENT_CI_FAILED",
                details=f"task_id={task.id}; commit={commit_sha}; ci={ci_status}",
            ))
            db.commit()
            processed += 1
        except CodingWorkspaceError as exc:
            db.rollback()
            logger.warning("Coding verification unavailable: task_id=%s status=%s", task.id, exc.status_code)
        except Exception as exc:
            db.rollback()
            logger.warning("Coding verification failed: task_id=%s error_type=%s", task.id, type(exc).__name__)
    return processed


CHIEF_OF_STAFF_CYCLE_KEY = "chief_of_staff.autonomous_cycle_at"
CHIEF_OF_STAFF_INTERVAL = timedelta(hours=24)
CHIEF_OF_STAFF_RETRY_INTERVAL = timedelta(minutes=30)
CHIEF_OF_STAFF_REQUESTED_BY = "MR AI Chief of Staff"
CHIEF_OF_STAFF_GOAL = (
    "Tafuta wateja wapya na fursa za biashara kwa MOOG Digital Printing & Branding "
    "Dar es Salaam. Lenga biashara, shule, taasisi, timu na waandaaji wanaoweza kuhitaji "
    "printing, branding, T-shirt, jersey, signage au graphic design. Tumia vyanzo vya "
    "umma, hifadhi ushahidi na viungo vya chanzo, ondoa nakala zinazojirudia, panga "
    "fursa kwa uhalisia wa huduma na toa mapendekezo ya hatua inayofuata. Usitume "
    "ujumbe, usipige simu, usichapishe wala kufanya malipo."
)
CHIEF_OF_STAFF_WAITING_STATES = {
    "PENDING", "RUNNING", "IN_PROGRESS", "WAITING", "VERIFYING",
    "WAITING_APPROVAL", "WAITING_FOR_HAND", "WAITING_FOR_VERIFICATION", "FAILED",
}
CHIEF_OF_STAFF_BLOCKED_STATES = {
    "PENDING", "WAITING", "VERIFYING", "WAITING_APPROVAL",
    "WAITING_FOR_HAND", "WAITING_FOR_VERIFICATION", "FAILED",
}


def _record_chief_of_staff_waiting_status(summary: dict[str, int], status: str) -> None:
    """Expose safe status counts so a blocked autonomous mission is diagnosable."""
    normalized = str(status or "").upper()
    if normalized == "PENDING":
        summary["missions_pending"] += 1
    elif normalized == "WAITING_FOR_HAND":
        summary["missions_waiting_for_hand"] += 1
    elif normalized == "WAITING_APPROVAL":
        summary["missions_waiting_for_approval"] += 1
    elif normalized == "WAITING_FOR_VERIFICATION":
        summary["missions_waiting_for_verification"] += 1
    elif normalized == "FAILED":
        summary["missions_failed"] += 1
    elif normalized in {"WAITING", "VERIFYING"}:
        summary["missions_other_waiting"] += 1


_CHIEF_OF_STAFF_LAST_HELD_LOG: dict[int, str] = {}


def _chief_of_staff_retry_block_reason(mission: Task, now: datetime) -> str:
    """Return a safe reason code explaining why an autonomous mission is not resumed."""
    status = str(mission.status or "").upper()
    if status not in {"WAITING_FOR_HAND", "FAILED"}:
        return "status_not_retryable"
    if mission.approved_by != mission.user_id:
        return "owner_approval_not_recorded"
    if mission.description != CHIEF_OF_STAFF_GOAL:
        return "goal_does_not_match"
    if mission.updated_at is None:
        return "updated_at_missing"
    try:
        packet = json.loads(mission.result or "{}")
    except (TypeError, ValueError):
        packet = {}
    if not isinstance(packet, dict):
        packet = {}
    plan = packet.get("plan")
    if isinstance(plan, dict):
        steps = plan.get("steps")
        if not isinstance(steps, list) or not steps:
            return "plan_steps_missing"
        if not all(
            isinstance(step, dict)
            and step.get("agent") == "research"
            and "searxng" in (step.get("tools") or [])
            for step in steps
        ):
            return "plan_contains_non_research_agent_or_missing_search_tool"
    if now - _as_utc_naive(mission.updated_at) < CHIEF_OF_STAFF_RETRY_INTERVAL:
        return "cooldown_active"
    if not isinstance(plan, dict):
        # Legacy packets are re-planned by execute_mission and must pass its strict
        # read-only recovery gate before any action can run.
        return "legacy_plan_requires_read_only_recheck"
    return "retry_eligible"


def _chief_of_staff_retry_allowed(mission: Task, now: datetime) -> bool:
    return _chief_of_staff_retry_block_reason(mission, now) in {
        "legacy_plan_requires_read_only_recheck",
        "retry_eligible",
    }


def _chief_of_staff_wait_diagnostics(mission: Task) -> tuple[str, str]:
    """Expose roles and statuses only; never log task prompts, email content or raw output."""
    try:
        packet = json.loads(mission.result or "{}")
    except (TypeError, ValueError):
        packet = {}
    if not isinstance(packet, dict):
        packet = {}
    plan = packet.get("plan") if isinstance(packet.get("plan"), dict) else {}
    planned_steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    executed_steps = packet.get("steps") if isinstance(packet.get("steps"), list) else []
    planned_agents = ",".join(
        f"{str(step.get('agent') or 'unknown')}:{','.join(str(tool) for tool in (step.get('tools') or [])[:4])}"
        for step in planned_steps[:7]
        if isinstance(step, dict)
    ) or "unknown"
    executed_states = ",".join(
        f"{str(step.get('agent') or 'unknown')}={str(step.get('status') or 'unknown').upper()}"
        for step in executed_steps[:7]
        if isinstance(step, dict)
    ) or "no_execution_steps"
    return planned_agents[:500], executed_states[:500]


def _log_chief_of_staff_held_mission(mission: Task, status: str, now: datetime) -> None:
    reason = _chief_of_staff_retry_block_reason(mission, now)
    planned_agents, executed_states = _chief_of_staff_wait_diagnostics(mission)
    marker = f"{status}|{reason}|{planned_agents}|{executed_states}"
    if _CHIEF_OF_STAFF_LAST_HELD_LOG.get(mission.id) == marker:
        return
    if len(_CHIEF_OF_STAFF_LAST_HELD_LOG) >= 256:
        _CHIEF_OF_STAFF_LAST_HELD_LOG.pop(next(iter(_CHIEF_OF_STAFF_LAST_HELD_LOG)))
    _CHIEF_OF_STAFF_LAST_HELD_LOG[mission.id] = marker
    logger.warning(
        "Chief of Staff mission held: task_id=%s status=%s reason=%s planned_agents=%s executed_steps=%s",
        mission.id,
        status,
        reason,
        planned_agents,
        executed_states,
    )


async def run_chief_of_staff_cycle(db: Session) -> dict[str, int]:
    """Start and safely resume the owner's MOOG research work without a chat command."""
    summary = {
        "users_checked": 0,
        "missions_started": 0,
        "missions_resumed": 0,
        "missions_completed": 0,
        "missions_waiting": 0,
        "missions_pending": 0,
        "missions_waiting_for_hand": 0,
        "missions_waiting_for_approval": 0,
        "missions_waiting_for_verification": 0,
        "missions_failed": 0,
        "missions_other_waiting": 0,
    }
    users = db.query(User).order_by(User.id.asc()).all()
    now = datetime.utcnow()
    for user in users:
        summary["users_checked"] += 1
        setting = db.query(Setting).filter(
            Setting.user_id == user.id, Setting.key == CHIEF_OF_STAFF_CYCLE_KEY
        ).order_by(Setting.id.desc()).first()
        last_run = None
        if setting and setting.value:
            try:
                last_run = _as_utc_naive(datetime.fromisoformat(setting.value))
            except (TypeError, ValueError):
                last_run = None

        active = db.query(Task).filter(
            Task.user_id == user.id,
            Task.agent == "orchestrator",
            Task.requested_by == CHIEF_OF_STAFF_REQUESTED_BY,
            Task.status.in_(CHIEF_OF_STAFF_WAITING_STATES),
        ).order_by(Task.created_at.desc(), Task.id.desc()).first()
        if active is not None:
            if _chief_of_staff_retry_allowed(active, now):
                try:
                    from .orchestration.executor import execute_mission
                    result = await execute_mission(CHIEF_OF_STAFF_GOAL, user, db, mission=active)
                    db.refresh(active)
                    status = str(active.status or (result or {}).get("status") or "").upper()
                    summary["missions_resumed"] += 1
                    summary["missions_completed"] += int(status == "COMPLETED")
                    summary["missions_waiting"] += int(status in CHIEF_OF_STAFF_BLOCKED_STATES)
                    _record_chief_of_staff_waiting_status(summary, status)
                    logger.info(
                        "Chief of Staff mission resumed: task_id=%s status=%s",
                        active.id,
                        status,
                    )
                    db.add(ActivityLog(
                        user_id=user.id,
                        action="CHIEF_OF_STAFF_MISSION_RESUMED",
                        details=f"task_id={active.id}; status={status}; retry_after_minutes=30",
                    ))
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    # Persist a cooldown even if the resume failed before the executor
                    # could update the task row; otherwise every scheduler tick retries it.
                    active.updated_at = now
                    active.error = "Chief of Staff resume failed; retry will occur after the cooldown."
                    db.add(ActivityLog(
                        user_id=user.id,
                        action="CHIEF_OF_STAFF_MISSION_RESUME_FAILED",
                        details=f"task_id={active.id}; error_type={type(exc).__name__}",
                    ))
                    db.commit()
                    summary["missions_waiting"] += 1
                    logger.error(
                        "Chief of Staff resume failed: task_id=%s error_type=%s",
                        active.id,
                        type(exc).__name__,
                    )
            else:
                status = str(active.status or "").upper()
                summary["missions_waiting"] += int(status in CHIEF_OF_STAFF_BLOCKED_STATES)
                _record_chief_of_staff_waiting_status(summary, status)
                _log_chief_of_staff_held_mission(active, status, now)
            continue

        if last_run and (now - last_run) < CHIEF_OF_STAFF_INTERVAL:
            continue
        try:
            from .orchestration.executor import execute_mission
            result = await execute_mission(CHIEF_OF_STAFF_GOAL, user, db)
            mission_data = result.get("mission") if isinstance(result, dict) else None
            mission_id = mission_data.get("id") if isinstance(mission_data, dict) else None
            if not mission_id:
                logger.warning("Chief of Staff did not create a mission: user_id=%s", user.id)
                continue
            mission = db.query(Task).filter(Task.id == mission_id, Task.user_id == user.id).first()
            if mission is not None:
                mission.requested_by = CHIEF_OF_STAFF_REQUESTED_BY
                db.add(ActivityLog(
                    user_id=user.id,
                    action="CHIEF_OF_STAFF_MISSION_STARTED",
                    details=f"task_id={mission.id}; scope=read_only_moog_lead_research; cadence_hours=24",
                ))
                status = str(mission.status or "").upper()
                summary["missions_completed"] += int(status == "COMPLETED")
                summary["missions_waiting"] += int(status in CHIEF_OF_STAFF_BLOCKED_STATES)
                _record_chief_of_staff_waiting_status(summary, status)
                summary["missions_started"] += 1
            if setting is None:
                db.add(Setting(user_id=user.id, key=CHIEF_OF_STAFF_CYCLE_KEY, value=now.isoformat()))
            else:
                setting.value = now.isoformat()
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Chief of Staff cycle failed: user_id=%s error_type=%s", user.id, type(exc).__name__)
    return summary


async def run_scheduler_cycle() -> tuple[int, int]:
    """Run one scheduler cycle at a time across poller and external wake-ups.

    The in-process polling loop and authenticated GitHub OIDC endpoint both call
    this function. Do not let a second invocation select and execute the same
    pending tasks while the current cycle is still working.
    """
    if _scheduler_cycle_lock.locked():
        logger.info("Scheduler cycle skipped: another cycle is already running")
        return 0, 0
    async with _scheduler_cycle_lock:
        return await _run_scheduler_cycle_once()


async def _run_scheduler_cycle_once() -> tuple[int, int]:
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
        "chief_of_staff_users_checked": 0,
        "chief_of_staff_missions_started": 0,
        "chief_of_staff_missions_resumed": 0,
        "chief_of_staff_missions_completed": 0,
        "chief_of_staff_missions_waiting": 0,
        "chief_of_staff_missions_pending": 0,
        "chief_of_staff_missions_waiting_for_hand": 0,
        "chief_of_staff_missions_waiting_for_approval": 0,
        "chief_of_staff_missions_waiting_for_verification": 0,
        "chief_of_staff_missions_failed": 0,
        "chief_of_staff_missions_other_waiting": 0,
        "coding_prs_verified": 0,
        "gmail_users_checked": 0,
        "gmail_messages_processed": 0,
        "gmail_drafts_created": 0,
        "gmail_replies_sent": 0,
        "gmail_followups_processed": 0,
        "gmail_assistant_errors": 0,
    }
    try:
        maybe_run_self_audit(db)
        try:
            chief_summary = await run_chief_of_staff_cycle(db)
            summary["chief_of_staff_users_checked"] = int(chief_summary.get("users_checked") or 0)
            summary["chief_of_staff_missions_started"] = int(chief_summary.get("missions_started") or 0)
            summary["chief_of_staff_missions_resumed"] = int(chief_summary.get("missions_resumed") or 0)
            summary["chief_of_staff_missions_completed"] = int(chief_summary.get("missions_completed") or 0)
            summary["chief_of_staff_missions_waiting"] = int(chief_summary.get("missions_waiting") or 0)
            summary["chief_of_staff_missions_pending"] = int(chief_summary.get("missions_pending") or 0)
            summary["chief_of_staff_missions_waiting_for_hand"] = int(chief_summary.get("missions_waiting_for_hand") or 0)
            summary["chief_of_staff_missions_waiting_for_approval"] = int(chief_summary.get("missions_waiting_for_approval") or 0)
            summary["chief_of_staff_missions_waiting_for_verification"] = int(chief_summary.get("missions_waiting_for_verification") or 0)
            summary["chief_of_staff_missions_failed"] = int(chief_summary.get("missions_failed") or 0)
            summary["chief_of_staff_missions_other_waiting"] = int(chief_summary.get("missions_other_waiting") or 0)
        except Exception as exc:
            db.rollback()
            logger.error("Chief of Staff mission cycle failed: error_type=%s", type(exc).__name__)

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
            summary["coding_prs_verified"] = await run_pending_coding_verifications(db, limit=5)
        except Exception as exc:
            db.rollback()
            logger.error("Coding Agent verification polling failed: error_type=%s", type(exc).__name__)

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
        if fired or processed or summary["autopilot_users_due"] or summary["approved_missions_processed"] or summary["chief_of_staff_missions_started"] or summary["gmail_messages_processed"] or summary["gmail_replies_sent"]:
            logger.info(
                "Scheduler cycle complete: triggered=%s processed=%s chief_missions=%s job_users=%s "
                "job_candidates=%s application_drafts=%s job_source_errors=%s",
                fired,
                processed,
                summary["chief_of_staff_missions_started"],
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
