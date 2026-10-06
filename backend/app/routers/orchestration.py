from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ApprovalRequest, Execution
from ..core.orchestrator import run

router = APIRouter(prefix="/orchestrator", tags=["Orchestrator"])

@router.post("/run")
async def run_command(payload: dict, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    text = str(payload.get("message", "")).strip()
    if not text:
        return {"status": "INVALID", "reason": "message is required"}
    return await run(current_user.id, text, db)

@router.get("/executions")
def executions(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Execution).filter(Execution.user_id == current_user.id).order_by(Execution.id.desc()).limit(50).all()

@router.get("/approvals")
def approvals(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(ApprovalRequest).filter(ApprovalRequest.user_id == current_user.id, ApprovalRequest.status == "PENDING").order_by(ApprovalRequest.id.desc()).all()


@router.post("/approvals/{approval_id}/resolve")
def resolve_approval(
    approval_id: int,
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    approval = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.id == approval_id, ApprovalRequest.user_id == current_user.id)
        .first()
    )
    if not approval:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Approval not found")

    decision = str(payload.get("decision", "")).upper()
    if decision not in {"APPROVE", "REJECT"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    approval.status = "APPROVED" if decision == "APPROVE" else "REJECTED"
    from datetime import datetime, timezone
    approval.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "status": approval.status,
        "approval_id": approval.id,
        "action": approval.action,
        "message": (
            "Approval recorded. The requested high-risk action still requires a connected execution hand."
            if decision == "APPROVE"
            else "Approval rejected; no action was executed."
        ),
    }
