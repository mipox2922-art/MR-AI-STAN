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
    reply_to_message,
    send_message,
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


@router.get("/gmail/assistant/status")
def gmail_assistant_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..gmail_assistant import get_assistant_status
    return get_assistant_status(db, current_user.id)


@router.get("/gmail/assistant/drafts")
def gmail_assistant_drafts(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..gmail_assistant import list_assistant_records
    return {"items": list_assistant_records(db, current_user.id, limit=50)}


@router.post("/gmail/assistant/config")
def gmail_assistant_config(
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..gmail_assistant import configure_assistant
    enabled = payload.get("enabled")
    auto_send_enabled = payload.get("auto_send_enabled")
    if enabled is not None and not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="'enabled' must be a boolean.")
    if auto_send_enabled is not None and not isinstance(auto_send_enabled, bool):
        raise HTTPException(status_code=400, detail="'auto_send_enabled' must be a boolean.")
    if enabled is None and auto_send_enabled is None:
        raise HTTPException(status_code=400, detail="Provide enabled and/or auto_send_enabled.")
    return configure_assistant(
        db,
        current_user.id,
        enabled=enabled,
        auto_send_enabled=auto_send_enabled,
    )


@router.post("/gmail/assistant/run")
async def gmail_assistant_run(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..gmail_assistant import run_gmail_assistant_for_user
    try:
        return await run_gmail_assistant_for_user(db, current_user.id, force=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Gmail assistant run failed: " + type(exc).__name__) from exc


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


@router.post("/gmail/messages/send")
async def gmail_send(
    payload: dict[str, str],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a plain-text Gmail message after explicit confirmation in the UI."""
    try:
        return await send_message(
            db,
            current_user.id,
            to=payload.get("to", ""),
            subject=payload.get("subject", ""),
            body=payload.get("body", ""),
        )
    except GmailConnectorError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/gmail/messages/{message_id}/reply")
async def gmail_reply(
    message_id: str,
    payload: dict[str, str],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reply to a Gmail message after explicit confirmation in the UI."""
    try:
        result = await reply_to_message(
            db,
            current_user.id,
            message_id,
            body=payload.get("body", ""),
        )
        try:
            from ..gmail_assistant import record_manual_reply_sent
            record_manual_reply_sent(db, current_user.id, message_id, result)
        except Exception:
            # Gmail already confirmed the send. Do not turn a tracking-only
            # persistence issue into a misleading failed-send response.
            db.rollback()
        return result
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
