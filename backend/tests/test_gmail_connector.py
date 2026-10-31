from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
import asyncio
import pytest

from app.connectors import gmail as gmail_module
from app.models import Integration
from app.connectors.gmail import (
    GMAIL_REFRESH_KEY,
    GMAIL_STATE_KEY,
    GmailConnectorError,
    _load_refresh_token,
    _normalize_message,
    _store_refresh_token,
    _access_token,
    connection_status,
    build_authorization_url,
)
from app.database import Base
from app.models import Setting


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_gmail_refresh_token_is_encrypted_at_rest():
    db = make_db()
    _store_refresh_token(db, 7, "refresh-secret-value")

    row = (
        db.query(Setting)
        .filter(Setting.user_id == 7, Setting.key == GMAIL_REFRESH_KEY)
        .first()
    )

    assert row is not None
    assert row.value != "refresh-secret-value"
    assert _load_refresh_token(db, 7) == "refresh-secret-value"


def test_gmail_authorization_url_uses_configured_scopes_offline_flow(monkeypatch):
    db = make_db()
    monkeypatch.setattr(settings, "gmail_client_id", "client-id")
    monkeypatch.setattr(settings, "gmail_client_secret", "client-secret")
    monkeypatch.setattr(settings, "gmail_redirect_uri", "http://localhost:8000/integrations/gmail/callback")
    monkeypatch.setattr(settings, "gmail_scopes", "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send")

    url = build_authorization_url(db, 42)
    query = parse_qs(urlparse(url).query)

    assert query["client_id"] == ["client-id"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"]
    assert query["state"][0].startswith("42:")

    state_row = (
        db.query(Setting)
        .filter(Setting.user_id == 42, Setting.key == GMAIL_STATE_KEY)
        .first()
    )
    assert state_row is not None


def test_gmail_message_normalization_extracts_headers():
    message = {
        "id": "msg-1",
        "threadId": "thread-1",
        "snippet": "Hello from Gmail",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Hello"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "boss@example.com"},
                {"name": "Date", "value": "Wed, 07 Oct 2026 12:00:00 +0000"},
            ],
            "body": {},
        },
    }

    normalized = _normalize_message(message)

    assert normalized["id"] == "msg-1"
    assert normalized["subject"] == "Hello"
    assert normalized["from"] == "sender@example.com"
    assert normalized["to"] == "boss@example.com"
    assert normalized["labels"] == ["INBOX", "UNREAD"]


def test_invalid_oauth_state_does_not_consume_the_valid_pending_state():
    db = make_db()
    from app.connectors.gmail import _set_oauth_state, _consume_oauth_state

    valid_state = _set_oauth_state(db, 9)

    try:
        _consume_oauth_state(db, 9, "wrong-state")
    except GmailConnectorError:
        pass
    else:
        raise AssertionError("Invalid OAuth state was accepted")

    row = (
        db.query(Setting)
        .filter(Setting.user_id == 9, Setting.key == GMAIL_STATE_KEY)
        .first()
    )
    assert row is not None, "A forged callback must not consume the legitimate state"

    _consume_oauth_state(db, 9, valid_state)
    row = (
        db.query(Setting)
        .filter(Setting.user_id == 9, Setting.key == GMAIL_STATE_KEY)
        .first()
    )
    assert row is None, "A valid one-time OAuth state should be consumed"



def test_transient_google_token_error_does_not_force_reauthorization(monkeypatch):
    db = make_db()
    _store_refresh_token(db, 7, "refresh-secret-value")

    class Response:
        is_error = True
        status_code = 503

        @staticmethod
        def json():
            return {"error": "server_error"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(gmail_module.httpx, "AsyncClient", lambda **kwargs: Client())
    try:
        asyncio.run(_access_token(db, 7))
    except GmailConnectorError as exc:
        assert "HTTP 503" in str(exc)
    else:
        raise AssertionError("A transient Google error must be surfaced")

    integration = db.query(Integration).filter(Integration.user_id == 7, Integration.name == "gmail").first()
    assert integration is None or integration.status != "REAUTH_REQUIRED"
    db.close()


def test_invalid_grant_marks_gmail_as_reauthorization_required(monkeypatch):
    db = make_db()
    _store_refresh_token(db, 8, "revoked-refresh-token")

    class Response:
        is_error = True
        status_code = 400

        @staticmethod
        def json():
            return {"error": "invalid_grant"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(gmail_module.httpx, "AsyncClient", lambda **kwargs: Client())
    with pytest.raises(GmailConnectorError, match="invalid_grant"):
        asyncio.run(_access_token(db, 8))

    status = connection_status_with_settings(db, 8)
    assert status["connected"] is False
    assert status["status"] == "REAUTH_REQUIRED"
    db.close()


def connection_status_with_settings(db, user_id):
    from app.config import settings
    settings.gmail_client_id = "client-id"
    settings.gmail_client_secret = "client-secret"
    settings.gmail_redirect_uri = "https://example.com/callback"
    return connection_status(db, user_id)
