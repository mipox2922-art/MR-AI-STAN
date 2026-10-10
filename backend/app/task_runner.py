from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .core.gateway import execute
from .core.intent import classify
from .core.permissions import create_approval
from .models import Task
from .realtime import manager

logger = logging.getLogger("mr_ai.task_runner")

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
        task.progress = max(task.progress or 0, 10)
        db.commit()
        db.refresh(task)

        text = (task.description or task.title or "").strip()
        intent = classify(text)

        if intent.name in HAND_STATUSES:
            task.status = "WAITING_FOR_HAND"
            task.progress = min(95, max(task.progress or 0, 25))
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
            task.progress = min(95, max(task.progress or 0, 20))
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
            task.progress = min(95, max(task.progress or 0, 20))
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

            if status == "COMPLETED":
                task.status = "COMPLETED"
                task.progress = 100
                task.error = None
                task.result = json.dumps(result, ensure_ascii=False, default=str)
            elif status in {"NOT_CONNECTED", "WAITING_FOR_HAND", "UNSUPPORTED"}:
                task.status = "WAITING_FOR_HAND"
                task.progress = min(95, max(task.progress or 0, 30))
                task.error = (
                    result.get("reason")
                    or result.get("message")
                    or "Required execution hand is unavailable."
                )
                task.result = json.dumps(result, ensure_ascii=False, default=str)
            else:
                task.status = "FAILED"
                task.error = result.get("reason") or result.get("message") or "Task execution failed."
                task.result = json.dumps(result, ensure_ascii=False, default=str)

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
                task.error = f"{type(exc).__name__}: {exc}"
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
            logger.exception("Task runner failed for task %s", task_id)
            processed += 1

    return processed
