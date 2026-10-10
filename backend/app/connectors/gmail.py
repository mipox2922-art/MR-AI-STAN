from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Integration, Setting


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_REFRESH_KEY = "integration.gmail.refresh_token"
GMAIL_STATE_KEY = "integration.gmail.oauth_state"
GMAIL_STATE_TTL_SECONDS = 600


class GmailConnectorError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(
        settings.gmail_client_id
        and settings.gmail_client_secret
        and settings.gmail_redirect_uri
    )


def scopes() -> list[str]:
    return [scope.strip() for scope in settings.gmail_scopes.split() if scope.strip()]


def _fernet() -> Fernet:
    # Derive a stable Fernet key from the application's runtime secret.
    # The refresh token remains server-side and is never returned to the UI.
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _get_setting(db: Session, user_id: int, key: str) -> Setting | None:
    return (
        db.query(Setting)
        .filter(Setting.user_id == user_id, Setting.key == key)
        .order_by(Setting.id.desc())
        .first()
    )


def _put_setting(db: Session, user_id: int, key: str, value: str) -> None:
    row = _get_setting(db, user_id, key)
    if row:
        row.value = value
    else:
        row = Setting(user_id=user_id, key=key, value=value)
        db.add(row)
    db.commit()


def _delete_setting(db: Session, user_id: int, key: str) -> None:
    row = _get_setting(db, user_id, key)
    if row:
        db.delete(row)
        db.commit()


def _store_refresh_token(db: Session, user_id: int, refresh_token: str) -> None:
    encrypted = _fernet().encrypt(refresh_token.encode("utf-8")).decode("utf-8")
    _put_setting(db, user_id, GMAIL_REFRESH_KEY, encrypted)


def _load_refresh_token(db: Session, user_id: int) -> str | None:
    row = _get_setting(db, user_id, GMAIL_REFRESH_KEY)
    if not row or not row.value:
        return None
    try:
        return _fernet().decrypt(row.value.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        raise GmailConnectorError("Stored Gmail credentials could not be decrypted.") from exc


def _set_oauth_state(db: Session, user_id: int) -> str:
    state = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=GMAIL_STATE_TTL_SECONDS)
    _put_setting(
        db,
        user_id,
        GMAIL_STATE_KEY,
        json.dumps({"state": state, "expires_at": expires_at.isoformat()}),
    )
    return state


def _consume_oauth_state(db: Session, user_id: int, state: str) -> None:
    row = _get_setting(db, user_id, GMAIL_STATE_KEY)
    if not row:
        raise GmailConnectorError("Gmail OAuth state is missing or expired.")

    try:
        payload = json.loads(row.value)
        expires_at = datetime.fromisoformat(payload["expires_at"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        _delete_setting(db, user_id, GMAIL_STATE_KEY)
        raise GmailConnectorError("Gmail OAuth state is invalid.") from exc

    if expires_at < datetime.now(timezone.utc):
        _delete_setting(db, user_id, GMAIL_STATE_KEY)
        raise GmailConnectorError("Gmail OAuth state is expired.")

    saved_state = str(payload.get("state", ""))
    if not secrets.compare_digest(saved_state, state):
        # A forged callback must not invalidate the real browser's pending OAuth flow.
        raise GmailConnectorError("Gmail OAuth state validation failed.")

    # Consume the one-time state only after it has passed all validation checks.
    _delete_setting(db, user_id, GMAIL_STATE_KEY)


def connection_status(db: Session, user_id: int) -> dict[str, Any]:
    configured = is_configured()
    connected = bool(_load_refresh_token(db, user_id)) if configured else False
    return {
        "configured": configured,
        "connected": connected,
        "scope": scopes(),
        "status": "CONNECTED" if connected else "AVAILABLE" if configured else "NOT_CONFIGURED",
    }


def build_authorization_url(db: Session, user_id: int) -> str:
    if not is_configured():
        raise GmailConnectorError("Gmail OAuth is not configured on the backend.")

    state = _set_oauth_state(db, user_id)
    params = {
        "client_id": settings.gmail_client_id,
        "redirect_uri": settings.gmail_redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes()),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": f"{user_id}:{state}",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(db: Session, code: str, state: str) -> dict[str, Any]:
    if not is_configured():
        raise GmailConnectorError("Gmail OAuth is not configured on the backend.")

    try:
        raw_user_id, raw_state = state.split(":", 1)
        user_id = int(raw_user_id)
    except (ValueError, AttributeError) as exc:
        raise GmailConnectorError("Invalid Gmail OAuth state.") from exc

    _consume_oauth_state(db, user_id, raw_state)

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.gmail_client_id,
                "client_secret": settings.gmail_client_secret,
                "redirect_uri": settings.gmail_redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if response.is_error:
        raise GmailConnectorError("Google OAuth token exchange failed.")

    payload = response.json()
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise GmailConnectorError(
            "Google did not return a refresh token. Re-authorize the Gmail connector."
        )

    _store_refresh_token(db, user_id, refresh_token)
    _mark_integration(db, user_id, "CONNECTED")
    return {"user_id": user_id, "status": "CONNECTED", "scope": scopes()}


def _mark_integration(db: Session, user_id: int, status: str) -> None:
    row = (
        db.query(Integration)
        .filter(Integration.user_id == user_id, Integration.name == "gmail")
        .first()
    )
    if row:
        row.status = status
    else:
        db.add(Integration(user_id=user_id, name="gmail", status=status))
    db.commit()


async def _access_token(db: Session, user_id: int) -> str:
    refresh_token = _load_refresh_token(db, user_id)
    if not refresh_token:
        raise GmailConnectorError("Gmail is not connected. Authorize the connector first.")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.gmail_client_id,
                "client_secret": settings.gmail_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

    if response.is_error:
        _mark_integration(db, user_id, "REAUTH_REQUIRED")
        raise GmailConnectorError("Gmail credentials were rejected. Re-authorize the connector.")

    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise GmailConnectorError("Google returned no Gmail access token.")
    _mark_integration(db, user_id, "CONNECTED")
    return token


async def _gmail_get(
    db: Session,
    user_id: int,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = await _access_token(db, user_id)

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{GMAIL_API_BASE}/{path.lstrip('/')}",
            params=params or {},
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code == 401:
            token = await _access_token(db, user_id)
            response = await client.get(
                f"{GMAIL_API_BASE}/{path.lstrip('/')}",
                params=params or {},
                headers={"Authorization": f"Bearer {token}"},
            )

    if response.is_error:
        detail = response.text[:500]
        raise GmailConnectorError(f"Gmail API request failed: {response.status_code} {detail}")
    return response.json()


def _header(headers: list[dict[str, str]], name: str) -> str:
    wanted = name.casefold()
    for item in headers:
        if str(item.get("name", "")).casefold() == wanted:
            return str(item.get("value", ""))
    return ""


def _decode_body(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8")).decode(
        "utf-8",
        errors="replace",
    )


def _extract_text(payload: dict[str, Any]) -> str:
    body = payload.get("body") or {}
    if body.get("data"):
        return _decode_body(body["data"])

    for part in payload.get("parts") or []:
        mime = str(part.get("mimeType", "")).casefold()
        text = _extract_text(part)
        if text and (mime == "text/plain" or not part.get("parts")):
            return text

    for part in payload.get("parts") or []:
        text = _extract_text(part)
        if text:
            return text

    return ""


def _normalize_message(payload: dict[str, Any], include_body: bool = False) -> dict[str, Any]:
    headers = payload.get("payload", {}).get("headers", [])
    row = {
        "id": payload.get("id"),
        "thread_id": payload.get("threadId"),
        "snippet": payload.get("snippet", ""),
        "subject": _header(headers, "Subject"),
        "from": _header(headers, "From"),
        "to": _header(headers, "To"),
        "date": _header(headers, "Date"),
        "labels": payload.get("labelIds", []),
    }

    if include_body:
        row["body_text"] = _extract_text(payload.get("payload") or {})
    return row


async def list_messages(
    db: Session,
    user_id: int,
    query: str = "",
    max_results: int = 20,
) -> dict[str, Any]:
    limit = max(1, min(int(max_results), 50))
    response = await _gmail_get(
        db,
        user_id,
        "/messages",
        params={"q": query[:500], "maxResults": limit},
    )
    summaries = []
    for message in response.get("messages", [])[:limit]:
        try:
            metadata = await _gmail_get(
                db,
                user_id,
                f"/messages/{message.get('id')}",
                params={
                    "format": "metadata",
                    "metadataHeaders": ["Subject", "From", "To", "Date"],
                },
            )
            summaries.append(_normalize_message(metadata))
        except GmailConnectorError:
            summaries.append({
                "id": message.get("id"),
                "thread_id": message.get("threadId"),
                "snippet": "",
                "subject": "",
                "from": "",
                "to": "",
                "date": "",
                "labels": [],
            })

    return {
        "status": "COMPLETED",
        "query": query[:500],
        "result_size_estimate": response.get("resultSizeEstimate", 0),
        "messages": summaries,
        "next_page_token": response.get("nextPageToken"),
    }


async def get_message(db: Session, user_id: int, message_id: str) -> dict[str, Any]:
    if not message_id or len(message_id) > 200:
        raise GmailConnectorError("Invalid Gmail message id.")

    response = await _gmail_get(
        db,
        user_id,
        f"/messages/{message_id}",
        params={"format": "full"},
    )
    return {
        "status": "COMPLETED",
        "message": _normalize_message(response, include_body=True),
    }


async def disconnect(db: Session, user_id: int) -> dict[str, Any]:
    _delete_setting(db, user_id, GMAIL_REFRESH_KEY)
    _delete_setting(db, user_id, GMAIL_STATE_KEY)
    _mark_integration(db, user_id, "NOT_CONNECTED")
    return {"status": "DISCONNECTED"}
