from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from .core.gateway import execute
from .core.intent import classify
from .models import Task
from .realtime import manager

logger = logging.getLogger("mr_ai.task_runner")

TERMINAL_STATUSES = {"COMPLETED", "FAILED"}
HAND_STATUSES = {"GMAIL_SEND", "GMAIL_SEARCH", "BROWSER_NAVIGATE", "FILE_DELETE", "SYSTEM_SHUTDOWN"}

async def run_pending_tasks(db: Session, limit: int = 5) -> int:
    """Process durable tasks that can be executed by verified backend hands.

    Tasks requiring a browser/device/local hand are left waiting instead of
    being reported as completed. High-risk intents are surfaced as approval
    requests by the normal orchestration permission boundary.
    """
    rows = (
        db.query(Task)
        .filter(Task.status == "PENDING")
        .order_by(Task.id.asc())
        .limit(max(1, min(limit, 20)))
        .all()
    )

    processed = 0

    for task in rows:
        # Claim before doing I/O so the same process does not execute a task twice.
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
                {"task_id": task.id, "status": task.status, "reason": task.error},
                user_id=task.user_id,
            )
            processed += 1
            continue

        if intent.name == "CHAT" or not intent.executable or intent.risk in {"HIGH", "CRITICAL"}:
            task.status = "WAITING_FOR_HAND" if intent.risk not in {"HIGH", "CRITICAL"} else "WAITING_APPROVAL"
            task.progress = min(95, max(task.progress or 0, 20))
            reason = (
                "No verified automatic execution hand exists for this command."
                if task.status == "WAITING_FOR_HAND"
                else "Explicit approval is required before this task can execute."
            )
            task.error = reason
            task.result = json.dumps(
                {"intent": intent.name, "risk": intent.risk, "reason": reason},
                ensure_ascii=False,
            )
            db.commit()
            await manager.broadcast(
                "TASK_WAITING",
                {"task_id": task.id, "status": task.status, "reason": reason},
                user_id=task.user_id,
            )
            processed += 1
            continue

        try:
            result = await execute(intent, task.user_id, db)
            status = str(result.get("status", "FAILED")).upper()

            if status == "COMPLETED":
                task.status = "COMPLETED"
                task.progress = 100
                task.error = None
                task.result = json.dumps(result, ensure_ascii=False, default=str)
            elif status in {"NOT_CONNECTED", "WAITING_FOR_HAND", "UNSUPPORTED"}:
                task.status = "WAITING_FOR_HAND"
                task.progress = min(95, max(task.progress or 0, 30))
                task.error = result.get("reason") or result.get("message") or "Required execution hand is unavailable."
                task.result = json.dumps(result, ensure_ascii=False, default=str)
            else:
                task.status = "FAILED"
                task.error = result.get("reason") or result.get("message") or "Task execution failed."
                task.result = json.dumps(result, ensure_ascii=False, default=str)

            db.commit()
            await manager.broadcast(
                "TASK_UPDATED",
                {
                    "task_id": task.id,
                    "status": task.status,
                    "progress": task.progress,
                    "result": task.result,
                    "error": task.error,
                },
                user_id=task.user_id,
            )
            processed += 1
        except Exception as exc:
            db.rollback()
            task = db.query(Task).filter(Task.id == task.id).first()
            if task:
                task.status = "FAILED"
                task.progress = min(95, max(task.progress or 0, 20))
                task.error = f"{type(exc).__name__}: {exc}"
                db.commit()
                await manager.broadcast(
                    "TASK_UPDATED",
                    {
                        "task_id": task.id,
                        "status": task.status,
                        "progress": task.progress,
                        "error": task.error,
                    },
                    user_id=task.user_id,
                )
            logger.exception("Task runner failed for task %s", getattr(task, "id", "?"))
            processed += 1

    return processed
