from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("")
def activity(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == current_user.id)
        .order_by(ActivityLog.id.desc())
        .limit(100)
        .all()
    )
