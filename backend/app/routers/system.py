from fastapi import APIRouter, Depends

from ..config import settings
from ..database import engine
from ..dependencies import get_current_user

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/status")
def system_status(
    current_user=Depends(get_current_user),
):
    return {
        "ai_core": "ONLINE",
        "database": "ONLINE",
        "voice": "ONLINE",
        "memory": "ONLINE",
        "web_app": "ONLINE",
        "extension": "ONLINE",
        "agents": "ONLINE",
        "gemini": (
            "ONLINE"
            if settings.gemini_api_key
            else "NOT_CONNECTED"
        ),
        "kimi": (
            "ONLINE"
            if settings.kimi_api_key
            else "NOT_CONNECTED"
        ),
    }
