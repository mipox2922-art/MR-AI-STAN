from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from ..models import Execution, ActivityLog, ApprovalRequest, Task, TaskStep
from ..audit import record_safe_error
from .intent import classify
from .permissions import check_permission, create_approval


async def run(user_id: int, text: str, db: Session) -> dict:
    """Plan-only orchestrator. Every created task waits for explicit owner approval."""
    started = time.perf_counter()
    request = str(text or "").strip()
    if not request:
        return {"status": "INVALID", "reason": "request is required"}

    intent = classify(request)
    decision = check_permission(db, user_id, intent.name, intent.risk)

    execution = Execution(
        user_id=user_id,
        intent=intent.name,
        status="WAITING_APPROVAL",
        risk=intent.risk,
    )
    db.add(execution)
    db.flush()

    mission = Task(
        user_id=user_id,
        title=request[:255],
        description=request[:12000],
        status="WAITING_APPROVAL",
        priority="HIGH" if intent.risk in {"HIGH", "CRITICAL"} else "NORMAL",
        agent="orchestrator",
        source="orchestrator",
        requested_by="MR AI Orchestrator",
        progress=0,
    )
    db.add(mission)
    db.flush()

    # Use the actual planner registry. Planned steps stay pending until Boss approves.
    from ..orchestration.planner import build_plan
    plan = build_plan(request)
    for index, plan_step in enumerate(plan.get("steps") or [], start=1):
        db.add(TaskStep(
            task_id=mission.id,
            position=index,
            title=str(plan_step.get("name") or plan_step.get("agent") or f"Hatua {index}")[:255],
            state="pending",
            evidence=None,
        ))

    approval_payload = {
        "task_id": mission.id,
        "execution_id": execution.id,
        "intent": intent.name,
        "parameters": intent.parameters,
    }
    approval = ApprovalRequest(
        user_id=user_id,
        action=intent.name,
        payload=json.dumps(approval_payload, ensure_ascii=False, default=str),
        status="PENDING",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(approval)
    execution.error = decision.reason if decision.requires_approval else "Owner approval is mandatory for every orchestrator-created task."
    execution.result = json.dumps({
        "task_id": mission.id,
        "approval_id": None,
        "status": "WAITING_APPROVAL",
        "execution_started": False,
    }, ensure_ascii=False)
    db.add(ActivityLog(
        user_id=user_id,
        action="ORCHESTRATION_PROPOSED",
        details=f"task_id={mission.id}; execution_id={execution.id}; intent={intent.name}; risk={intent.risk}",
    ))
    db.commit()
    db.refresh(execution)
    db.refresh(mission)
    db.refresh(approval)

    execution.result = json.dumps({
        "task_id": mission.id,
        "approval_id": approval.id,
        "status": "WAITING_APPROVAL",
        "execution_started": False,
    }, ensure_ascii=False)
    db.commit()

    return {
        "status": "WAITING_APPROVAL",
        "execution_id": execution.id,
        "task_id": mission.id,
        "approval_id": approval.id,
        "intent": intent.name,
        "confidence": intent.confidence,
        "risk": intent.risk,
        "reason": "Boss Ferisi lazima aidhinishe kabla ya hatua yoyote kutekelezwa.",
        "execution_started": False,
        "plan": plan,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
