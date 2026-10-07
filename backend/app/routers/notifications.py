from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Notification
from ..realtime import manager

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _serialize(row: Notification) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "message": row.message,
        "read": bool(row.read),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("")
def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    size = max(1, min(int(limit), 100))
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.read.is_(False))

    rows = query.order_by(Notification.id.desc()).limit(size).all()
    return {
        "notifications": [_serialize(row) for row in rows],
        "unread_count": db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.read.is_(False))
        .count(),
    }


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Notification not found")

    row.read = True
    db.commit()

    await manager.broadcast(
        "NOTIFICATION_READ",
        {"notification_id": row.id},
        user_id=current_user.id,
    )
    return _serialize(row)


@router.post("/read-all")
async def mark_all_read(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.read.is_(False))
        .all()
    )
    changed = len(rows)
    for row in rows:
        row.read = True
    db.commit()

    await manager.broadcast(
        "NOTIFICATIONS_READ_ALL",
        {"count": changed, "at": datetime.now(timezone.utc).isoformat()},
        user_id=current_user.id,
    )
    return {"status": "COMPLETED", "changed": changed}
