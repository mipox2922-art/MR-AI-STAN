from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .core.gateway import execute
from .core.intent import classify
from .core.permissions import create_approval
from .models import Task, TaskStep
from .audit import record_safe_error, redact_sensitive_text
from .realtime import manager

logger = logging.getLogger("mr_ai.task_runner")


def _progress_from_steps(db: Session, task_id: int) -> tuple[int, int, int]:
    steps = db.query(TaskStep).filter(TaskStep.task_id == task_id).all()
    if not steps:
        return 0, 0, 0
    verified = sum(str(step.state or "").lower() == "verified" and bool(str(step.evidence or "").strip()) for step in steps)
    return int(verified / len(steps) * 100), verified, len(steps)


def _record_execution_step(db: Session, task: Task, title: str, evidence: object, verified: bool) -> None:
    encoded = json.dumps(evidence, ensure_ascii=False, default=str)
    current = db.query(TaskStep).filter(TaskStep.task_id == task.id).all()
    position = max((step.position for step in current), default=0) + 1
    db.add(TaskStep(
        task_id=task.id,
        position=position,
        title=str(title or "Backend execution result")[:255],
        state="verified" if verified and encoded.strip() else "failed" if not verified else "pending",
        evidence=encoded if encoded.strip() else None,
        verified_at=datetime.utcnow() if verified and encoded.strip() else None,
    ))
    db.flush()

HAND_STATUSES = {
    "GMAIL_SEARCH",
    "BROWSER_NAVIGATE",
}


async def run_pending_tasks(db: Session, limit: int = 5) -> int:
    stale_cutoff = datetime.utcnow() - timedelta(minutes=15)
    rows = (
        db.query(Task)
        .filter(
            Task.agent == "scheduler",
            or_(
                Task.status == "PENDING",
                and_(
                    Task.status == "RUNNING",
                    Task.updated_at < stale_cutoff,
                ),
            ),
        )
        .order_by(Task.id.asc())
        .limit(max(1, min(limit, 20)))
        .all()
    )

    processed = 0

    for task in rows:
        task_id = task.id
        user_id = task.user_id
        task.status = "RUNNING"
        task.progress = _progress_from_steps(db, task.id)[0]
        db.commit()
        db.refresh(task)

        text = (task.description or task.title or "").strip()
        intent = classify(text)

        if intent.name == "JOB_RESEARCH":
            import re
            from .routers.jobs import research_public_jobs

            query = re.sub(r"^\[scheduled\]\s*", "", text, flags=re.IGNORECASE)
            query = re.sub(
                r"^(?:job research|research jobs|search jobs|find jobs|remote jobs|ajira)(?:\s+(?:for|in))?\s*[:,-]?\s*",
                "",
                query,
                flags=re.IGNORECASE,
            ).strip()
            query = query or "remote jobs"
            try:
                result = await research_public_jobs(query, limit=15)
                result_status = str(result.get("status", "FAILED")).upper()
                succeeded = result_status in {"COMPLETED", "NO_RESULTS"}
                task.status = "COMPLETED" if succeeded else "FAILED"
                task.error = None if succeeded else redact_sensitive_text(result.get("message") or "Job feed did not return a completed status.", 500)
                task.result = json.dumps(result, ensure_ascii=False, default=str)
                _record_execution_step(db, task, "Utafutaji wa ajira kupitia public feeds", result, succeeded)
                progress, _, _ = _progress_from_steps(db, task.id)
                task.progress = progress
            except Exception as exc:
                task.status = "FAILED"
                task.error = f"Job research failed: {type(exc).__name__}"
                task.result = json.dumps({"status": "FAILED", "query": query}, ensure_ascii=False)
                record_safe_error(db, user_id, "task_runner.job_research", type(exc).__name__, "Public job search failed; task details and message content omitted.")
            db.commit()
            await manager.broadcast(
                "TASK_UPDATED",
                {
                    "task_id": task_id,
                    "status": task.status,
                    "progress": task.progress,
                    "result": task.result,
                    "error": task.error,
                },
                user_id=user_id,
            )
            processed += 1
            continue

        if intent.name in HAND_STATUSES:
            task.status = "WAITING_FOR_HAND"
            task.progress = _progress_from_steps(db, task.id)[0]
            task.error = "A connected permissioned execution hand is required."
            task.result = json.dumps(
                {"intent": intent.name, "reason": task.error},
                ensure_ascii=False,
            )
            db.commit()
            await manager.broadcast(
                "TASK_WAITING",
                {"task_id": task_id, "status": task.status, "reason": task.error},
                user_id=user_id,
            )
            processed += 1
            continue

        if intent.risk in {"HIGH", "CRITICAL"}:
            approval = create_approval(
                db,
                user_id,
                intent.name,
                json.dumps(
                    {
                        "task_id": task_id,
                        "intent": intent.name,
                        "parameters": intent.parameters,
                    },
                    ensure_ascii=False,
                ),
            )
            task.status = "WAITING_APPROVAL"
            task.progress = _progress_from_steps(db, task.id)[0]
            task.error = "Explicit approval is required before this scheduled task can proceed."
            task.result = json.dumps(
                {
                    "intent": intent.name,
                    "approval_id": approval.id,
                    "reason": task.error,
                },
                ensure_ascii=False,
            )
            db.commit()
            await manager.broadcast(
                "TASK_WAITING",
                {
                    "task_id": task_id,
                    "status": task.status,
                    "approval_id": approval.id,
                    "reason": task.error,
                },
                user_id=user_id,
            )
            processed += 1
            continue

        if intent.name == "CHAT" or not intent.executable:
            task.status = "WAITING_FOR_HAND"
            task.progress = _progress_from_steps(db, task.id)[0]
            task.error = "No verified automatic execution hand exists for this command."
            task.result = json.dumps(
                {"intent": intent.name, "reason": task.error},
                ensure_ascii=False,
            )
            db.commit()
            await manager.broadcast(
                "TASK_WAITING",
                {"task_id": task_id, "status": task.status, "reason": task.error},
                user_id=user_id,
            )
            processed += 1
            continue

        try:
            result = await execute(intent, user_id, db)
            status = str(result.get("status", "FAILED")).upper()

            encoded_result = json.dumps(result, ensure_ascii=False, default=str)
            if status == "COMPLETED":
                task.error = None
                task.result = encoded_result
                _record_execution_step(db, task, f"Backend execution: {intent.name}", result, True)
                progress, verified, total = _progress_from_steps(db, task.id)
                task.progress = progress
                task.status = "COMPLETED" if total > 0 and verified == total else "WAITING_FOR_VERIFICATION"
            elif status in {"NOT_CONNECTED", "WAITING_FOR_HAND", "UNSUPPORTED"}:
                task.status = "WAITING_FOR_HAND"
                task.progress = _progress_from_steps(db, task.id)[0]
                task.error = redact_sensitive_text(result.get("reason") or result.get("message") or "Required execution hand is unavailable.", 500)
                task.result = encoded_result
            else:
                task.status = "FAILED"
                task.error = redact_sensitive_text(result.get("reason") or result.get("message") or "Task execution failed.", 500)
                task.result = encoded_result
                record_safe_error(db, user_id, "task_runner.execution", status, "Task execution returned a failure status; raw input omitted.")

            db.commit()
            await manager.broadcast(
                "TASK_UPDATED",
                {
                    "task_id": task_id,
                    "status": task.status,
                    "progress": task.progress,
                    "result": task.result,
                    "error": task.error,
                },
                user_id=user_id,
            )
            processed += 1
        except Exception as exc:
            db.rollback()
            task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
            if task:
                task.status = "FAILED"
                task.progress = min(95, max(task.progress or 0, 20))
                task.error = f"{type(exc).__name__}: task execution failed; inspect the safe error log."
                db.commit()
                await manager.broadcast(
                    "TASK_UPDATED",
                    {
                        "task_id": task_id,
                        "status": task.status,
                        "progress": task.progress,
                        "error": task.error,
                    },
                    user_id=user_id,
                )
            record_safe_error(db, user_id, "task_runner", type(exc).__name__, "Task execution raised an exception; raw prompt, task content and credentials were not logged.")
            logger.error("Task runner failed: task_id=%s error_type=%s", task_id, type(exc).__name__)
            processed += 1

    return processed
