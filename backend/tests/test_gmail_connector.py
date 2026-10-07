from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.connectors.gmail import (
    GMAIL_REFRESH_KEY,
    GMAIL_STATE_KEY,
    GmailConnectorError,
    _load_refresh_token,
    _normalize_message,
    _store_refresh_token,
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


def test_gmail_authorization_url_uses_readonly_offline_flow(monkeypatch):
    db = make_db()
    monkeypatch.setattr(settings, "gmail_client_id", "client-id")
    monkeypatch.setattr(settings, "gmail_client_secret", "client-secret")
    monkeypatch.setattr(settings, "gmail_redirect_uri", "http://localhost:8000/integrations/gmail/callback")
    monkeypatch.setattr(settings, "gmail_scopes", "https://www.googleapis.com/auth/gmail.readonly")

    url = build_authorization_url(db, 42)
    query = parse_qs(urlparse(url).query)

    assert query["client_id"] == ["client-id"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
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


def test_invalid_oauth_state_is_rejected():
    db = make_db()
    from app.connectors.gmail import _set_oauth_state, _consume_oauth_state

    _set_oauth_state(db, 9)

    try:
        _consume_oauth_state(db, 9, "wrong-state")
    except GmailConnectorError:
        return

    raise AssertionError("Invalid OAuth state was accepted")
