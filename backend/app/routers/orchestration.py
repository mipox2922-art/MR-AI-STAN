from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.orchestrator import run
from ..database import get_db
from ..dependencies import get_current_user
from ..models import ApprovalRequest, Task, Execution
from ..core.authorizations import (
    POLICY_DEFINITIONS,
    list_standing_authorizations,
    set_standing_authorization,
)

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


@router.get("/authorizations")
def get_authorizations(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return only the authenticated owner's standing authorization rules."""
    return list_standing_authorizations(db, current_user.id)


@router.put("/authorizations/{policy_id}")
def update_authorization(
    policy_id: str,
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enable/disable one fixed, narrowly scoped standing authorization."""
    if policy_id not in POLICY_DEFINITIONS:
        raise HTTPException(status_code=404, detail="Standing authorization policy not found.")
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool) or set(payload.keys()) != {"enabled"}:
        raise HTTPException(status_code=422, detail="Provide exactly one boolean field: enabled.")
    try:
        return set_standing_authorization(db, current_user.id, policy_id, enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    try:
        details = json.loads(approval.payload or "{}")
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
            if decision == "REJECT":
                task.status = "FAILED"
                task.progress = 0
                task.error = "Pendekezo limekataliwa na Boss Ferisi; hakuna kitendo kilichotekelezwa."
                task.result = json.dumps({"approval_id": approval.id, "approved": False}, ensure_ascii=False)
            elif task.agent == "orchestrator":
                # An explicit Start action is still required after approval.
                task.status = "PENDING"
                task.approved_by = current_user.id
                task.approved_at = _now_utc().replace(tzinfo=None)
                task.error = None
                task.result = json.dumps({"approval_id": approval.id, "approved": True, "started": False}, ensure_ascii=False)
            else:
                # Approved agent work remains blocked until a verified execution hand is available.
                task.status = "WAITING_FOR_HAND"
                task.approved_by = current_user.id
                task.approved_at = _now_utc().replace(tzinfo=None)
                task.error = "Idhini imerekodiwa. Bado inahitaji execution hand iliyoidhinishwa."
                task.result = json.dumps({"approval_id": approval.id, "approved": True, "started": False}, ensure_ascii=False)
            follow_up = {"task_id": task.id, "status": task.status, "approved_by": task.approved_by}

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
