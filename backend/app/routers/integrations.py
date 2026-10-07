from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..connectors.gmail import (
    GmailConnectorError,
    build_authorization_url,
    connection_status,
    disconnect,
    exchange_code,
    get_message,
    is_configured,
    list_messages,
)
from ..database import get_db
from ..dependencies import get_current_user


router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("/gmail/status")
def gmail_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return connection_status(db, current_user.id)


@router.get("/gmail/connect")
def gmail_connect(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="Gmail OAuth is not configured on the backend.",
        )

    try:
        return {
            "status": "AUTHORIZATION_REQUIRED",
            "authorization_url": build_authorization_url(db, current_user.id),
        }
    except GmailConnectorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/gmail/callback")
async def gmail_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        return JSONResponse(
            status_code=400,
            content={"status": "DENIED", "error": error[:200]},
        )

    if not code or not state:
        raise HTTPException(status_code=400, detail="Gmail OAuth callback is incomplete.")

    try:
        result = await exchange_code(db, code, state)
        return {
            "status": "CONNECTED",
            "user_id": result["user_id"],
            "scope": result["scope"],
            "message": "Gmail connected. You can close this window and return to MR AI.",
        }
    except GmailConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/gmail/messages")
async def gmail_messages(
    q: str = "",
    max_results: int = 20,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return await list_messages(db, current_user.id, q=q, max_results=max_results)
    except GmailConnectorError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/gmail/messages/{message_id}")
async def gmail_message(
    message_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return await get_message(db, current_user.id, message_id)
    except GmailConnectorError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/gmail")
def gmail_disconnect(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return disconnect(db, current_user.id)
    except GmailConnectorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
