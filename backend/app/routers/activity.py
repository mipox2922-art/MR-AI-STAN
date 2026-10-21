import json
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog

router = APIRouter(prefix="/activity", tags=["Activity"])

_ALLOWED_COMPONENTS = {"browser", "device", "security", "task", "ai"}
_ALLOWED_OUTCOMES = {
    "REQUESTED", "APPROVAL_REQUIRED", "APPROVED", "REJECTED",
    "DISPATCHED_UNVERIFIED", "VERIFIED", "FAILED", "BLOCKED",
}
_ALLOWED_RISKS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_SAFE_ACTION = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_SAFE_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$", re.I)


@router.get("")
def activity(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == current_user.id)
        .order_by(ActivityLog.id.desc())
        .limit(100)
        .all()
    )


@router.post("/events")
def record_activity_event(
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record action lifecycle metadata only; reject raw message/body/secret fields."""
    if any(key in payload for key in ("message", "content", "body", "token", "api_key", "password", "prompt")):
        raise HTTPException(400, "Audit events accept metadata only, not message content or credentials.")

    component = str(payload.get("component") or "").strip().lower()
    action = str(payload.get("action") or "").strip()
    outcome = str(payload.get("outcome") or "").strip().upper()
    risk = str(payload.get("risk") or "MEDIUM").strip().upper()
    target_host = str(payload.get("target_host") or "").strip().lower()
    request_id = str(payload.get("request_id") or "").strip()[:100]

    if component not in _ALLOWED_COMPONENTS:
        raise HTTPException(400, "Unsupported audit component.")
    if not _SAFE_ACTION.fullmatch(action):
        raise HTTPException(400, "Action must be a short identifier; raw action text is not accepted.")
    if outcome not in _ALLOWED_OUTCOMES:
        raise HTTPException(400, "Unsupported action outcome.")
    if risk not in _ALLOWED_RISKS:
        raise HTTPException(400, "Unsupported risk classification.")
    if target_host and not _SAFE_HOST.fullmatch(target_host):
        raise HTTPException(400, "Target host must be a hostname, not a URL or free text.")

    # Explicit keys only; no user-provided prose is written to audit logs.
    details = json.dumps({
        "component": component,
        "action": action,
        "outcome": outcome,
        "risk": risk,
        "target_host": target_host or None,
        "request_id": request_id or None,
    }, ensure_ascii=False, separators=(",", ":"))
    row = ActivityLog(user_id=current_user.id, action="SECURITY_ACTION_AUDIT", details=details)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "RECORDED", "event_id": row.id, "action": action, "outcome": outcome}
