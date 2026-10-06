from __future__ import annotations

import json
import time
from sqlalchemy.orm import Session

from ..models import Execution, ActivityLog
from .intent import classify
from .permissions import check_permission, create_approval
from .gateway import execute

async def run(user_id: int, text: str, db: Session) -> dict:
    started = time.perf_counter()
    intent = classify(text)
    decision = check_permission(db, user_id, intent.name, intent.risk)

    execution = Execution(
        user_id=user_id,
        intent=intent.name,
        status="PLANNED",
        risk=intent.risk,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    if decision.requires_approval:
        approval = create_approval(db, user_id, intent.name, json.dumps(intent.parameters))
        execution.status = "WAITING_APPROVAL"
        execution.error = decision.reason
        db.commit()
        return {
            "status": "WAITING_APPROVAL",
            "execution_id": execution.id,
            "approval_id": approval.id,
            "intent": intent.name,
            "confidence": intent.confidence,
            "reason": decision.reason,
        }

    execution.status = "RUNNING"
    db.commit()

    try:
        result = await execute(intent, user_id, db)
        execution.status = "COMPLETED" if result.get("status") == "COMPLETED" else result.get("status", "FAILED")
        execution.result = json.dumps(result, default=str)
        db.add(ActivityLog(user_id=user_id, action="ORCHESTRATION", details=f"{intent.name}:{execution.status}"))
        db.commit()
        return {
            "status": execution.status,
            "execution_id": execution.id,
            "intent": intent.name,
            "confidence": intent.confidence,
            "result": result,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        db.rollback()
        execution.status = "FAILED"
        execution.error = f"{type(exc).__name__}: {exc}"
        db.add(execution)
        db.commit()
        return {
            "status": "FAILED",
            "execution_id": execution.id,
            "intent": intent.name,
            "confidence": intent.confidence,
            "error": execution.error,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
