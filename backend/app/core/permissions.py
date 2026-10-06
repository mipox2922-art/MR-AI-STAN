from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from ..models import ApprovalRequest

@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requires_approval: bool
    reason: str

HIGH_RISK = {"HIGH", "CRITICAL"}

def check_permission(db: Session, user_id: int, action: str, risk: str) -> PermissionDecision:
    if risk not in HIGH_RISK:
        return PermissionDecision(True, False, "low-risk action")
    return PermissionDecision(False, True, f"Explicit approval required for {action}")

def create_approval(db: Session, user_id: int, action: str, payload: str) -> ApprovalRequest:
    approval = ApprovalRequest(
        user_id=user_id,
        action=action,
        payload=payload,
        status="PENDING",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval
