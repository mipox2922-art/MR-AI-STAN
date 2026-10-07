from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.orchestrator import run
from ..database import get_db
from ..dependencies import get_current_user
from ..models import ApprovalRequest, Task, Execution

router = APIRouter(prefix="/orchestrator", tags=["Orchestrator"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _expire_if_needed(approval: ApprovalRequest) -> bool:
    if approval.status != "PENDING" or not approval.expires_at:
        return False
    expires_at = approval.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _now_utc():
        approval.status = "EXPIRED"
        approval.resolved_at = _now_utc()
        return True
    return False


@router.post("/run")
async def run_command(
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    text = str(payload.get("message", "")).strip()
    if not text:
        return {"status": "INVALID", "reason": "message is required"}
    return await run(current_user.id, text, db)


@router.get("/executions")
def executions(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Execution)
        .filter(Execution.user_id == current_user.id)
        .order_by(Execution.id.desc())
        .limit(50)
        .all()
    )


@router.get("/approvals")
def approvals(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ApprovalRequest)
        .filter(
            ApprovalRequest.user_id == current_user.id,
            ApprovalRequest.status == "PENDING",
        )
        .order_by(ApprovalRequest.id.desc())
        .all()
    )

    changed = any(_expire_if_needed(row) for row in rows)
    if changed:
        db.commit()

    return [
        row
        for row in rows
        if row.status == "PENDING"
    ]


@router.post("/approvals/{approval_id}/resolve")
def resolve_approval(
    approval_id: int,
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    approval = (
        db.query(ApprovalRequest)
        .filter(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.user_id == current_user.id,
        )
        .first()
    )
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    if _expire_if_needed(approval):
        db.commit()
        raise HTTPException(status_code=409, detail="Approval has expired")

    if approval.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Approval is already {approval.status}")

    decision = str(payload.get("decision", "")).upper()
    if decision not in {"APPROVE", "REJECT"}:
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    approval.status = "APPROVED" if decision == "APPROVE" else "REJECTED"
    approval.resolved_at = _now_utc()

    follow_up = None
    if decision == "APPROVE":
        try:
            details = json.loads(approval.payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            details = {}

        task_id = details.get("task_id")
        if isinstance(task_id, int):
            task = (
                db.query(Task)
                .filter(Task.id == task_id, Task.user_id == current_user.id)
                .first()
            )
            if task and task.status == "WAITING_APPROVAL":
                task.status = "WAITING_FOR_HAND"
                task.error = "Approval granted. The connected external execution hand must perform this action."
                task.result = json.dumps(
                    {"approval_id": approval.id, "approved": True},
                    ensure_ascii=False,
                )
                follow_up = {
                    "task_id": task.id,
                    "status": task.status,
                }

    db.commit()

    return {
        "status": approval.status,
        "approval_id": approval.id,
        "action": approval.action,
        "follow_up": follow_up,
        "message": (
            "Approval recorded. High-impact execution still requires its connected permissioned hand."
            if decision == "APPROVE"
            else "Approval rejected; no action was executed."
        ),
    }
