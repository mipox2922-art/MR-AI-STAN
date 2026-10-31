import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Task, User
from app import gmail_assistant


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    user = User(username="boss-ferisi", password_hash="test-only")
    db.add(user)
    db.commit()
    db.refresh(user)
    return db, user


def fake_email():
    return {
        "id": "message-1",
        "thread_id": "thread-1",
        "from": "colleague@example.com",
        "to": "boss@example.com",
        "subject": "Quick catch-up",
        "date": "Tue, 28 Oct 2026 09:00:00 +0000",
        "body_text": "Hello, could we schedule a short catch-up next week?",
        "snippet": "Hello, could we schedule a short catch-up next week?",
        "labels": ["INBOX", "UNREAD"],
    }


def install_fake_gmail(monkeypatch, message=None):
    from app.connectors import gmail

    value = message or fake_email()
    monkeypatch.setattr(
        gmail, "connection_status",
        lambda db, user_id: {"connected": True, "configured": True},
    )

    async def list_messages(db, user_id, query="", max_results=20):
        assert query == "in:inbox is:unread"
        return {
            "status": "COMPLETED",
            "messages": [{
                "id": value["id"],
                "thread_id": value["thread_id"],
                "from": value["from"],
                "subject": value["subject"],
                "date": value["date"],
                "snippet": value["snippet"],
            }],
        }

    async def get_message(db, user_id, message_id):
        assert message_id == value["id"]
        return {"status": "COMPLETED", "message": value}

    sent = []

    async def reply_to_message(db, user_id, message_id, body):
        sent.append({"user_id": user_id, "message_id": message_id, "body": body})
        return {
            "status": "SENT",
            "message_id": "sent-message-1",
            "thread_id": value["thread_id"],
        }

    async def get_thread(db, user_id, thread_id):
        return {"status": "COMPLETED", "id": thread_id, "messages": [value]}

    monkeypatch.setattr(gmail, "list_messages", list_messages)
    monkeypatch.setattr(gmail, "get_message", get_message)
    monkeypatch.setattr(gmail, "reply_to_message", reply_to_message)
    monkeypatch.setattr(gmail, "get_thread", get_thread)
    return sent


def install_fake_ai(monkeypatch, *, action="reply", confidence=0.95):
    async def generate(primary, prompt, timeout=40):
        assert "untrusted email data" in prompt.lower()
        return json.dumps({
            "action": action,
            "confidence": confidence,
            "summary": "A colleague asks to arrange a short catch-up.",
            "reply_draft": "Thanks for reaching out. Let us arrange a suitable time next week.",
            "follow_up_note": "Check whether the sender confirms a time.",
            "needs_follow_up": True,
        }), primary

    monkeypatch.setattr(gmail_assistant, "_preferred_provider", lambda: "openrouter")
    monkeypatch.setattr("app.routers.ai.generate_reply_with_fallback", generate)


def test_gmail_background_provider_prefers_explicit_free_openrouter(monkeypatch):
    monkeypatch.setattr(gmail_assistant.settings, "openrouter_api_key", "test-openrouter-key")
    monkeypatch.setattr(gmail_assistant.settings, "openrouter_model", "openrouter/free")
    monkeypatch.setattr(gmail_assistant.settings, "gemini_api_key", "test-gemini-key")
    monkeypatch.setattr(gmail_assistant.settings, "gemini_tier", "FREE")
    monkeypatch.setattr(gmail_assistant.settings, "mistral_api_key", "paid-mistral-key")
    monkeypatch.setattr(gmail_assistant.settings, "kimi_api_key", "paid-kimi-key")
    monkeypatch.setattr(gmail_assistant.settings, "xai_api_key", "paid-grok-key")

    assert gmail_assistant._preferred_provider() == "openrouter"


def test_gmail_background_provider_does_not_select_paid_keys(monkeypatch):
    monkeypatch.setattr(gmail_assistant.settings, "openrouter_api_key", "test-openrouter-key")
    monkeypatch.setattr(gmail_assistant.settings, "openrouter_model", "provider/paid-model")
    monkeypatch.setattr(gmail_assistant.settings, "gemini_api_key", "test-gemini-key")
    monkeypatch.setattr(gmail_assistant.settings, "gemini_tier", "PAID")
    monkeypatch.setattr(gmail_assistant.settings, "mistral_api_key", "paid-mistral-key")
    monkeypatch.setattr(gmail_assistant.settings, "kimi_api_key", "paid-kimi-key")
    monkeypatch.setattr(gmail_assistant.settings, "xai_api_key", "paid-grok-key")

    assert gmail_assistant._preferred_provider() is None


def test_gmail_assistant_saves_reply_draft_and_deduplicates(monkeypatch):
    db, user = make_db()
    sent = install_fake_gmail(monkeypatch)
    install_fake_ai(monkeypatch)

    result = asyncio.run(gmail_assistant.run_gmail_assistant_for_user(db, user.id, force=True))

    assert result["status"] == "COMPLETED"
    assert result["summary"]["messages_processed"] == 1
    assert result["summary"]["drafts_created"] == 1
    assert sent == []
    record = gmail_assistant._load_record(db, user.id, "message-1")
    assert record["status"] == "DRAFT_READY"
    assert record["reply_draft"].startswith("Thanks for reaching out")
    assert db.query(Task).filter(Task.user_id == user.id).count() == 1
    draft_task = db.query(Task).filter(Task.user_id == user.id).one()
    assert draft_task.status == "READY_FOR_REVIEW"

    again = asyncio.run(gmail_assistant.run_gmail_assistant_for_user(db, user.id, force=True))
    assert again["summary"]["messages_processed"] == 0
    assert db.query(Task).filter(Task.user_id == user.id).count() == 1
    db.close()


def test_gmail_assistant_only_auto_sends_after_explicit_opt_in(monkeypatch):
    db, user = make_db()
    sent = install_fake_gmail(monkeypatch)
    install_fake_ai(monkeypatch)
    gmail_assistant.configure_assistant(db, user.id, enabled=True, auto_send_enabled=True)

    result = asyncio.run(gmail_assistant.run_gmail_assistant_for_user(db, user.id, force=True))

    assert result["summary"]["replies_sent"] == 1
    assert len(sent) == 1
    record = gmail_assistant._load_record(db, user.id, "message-1")
    assert record["status"] == "SENT_WAITING_REPLY"
    assert record["sent_message_id"] == "sent-message-1"
    assert record["follow_up_at"]
    db.close()


def test_gmail_assistant_never_auto_sends_sensitive_messages(monkeypatch):
    db, user = make_db()
    message = fake_email()
    message["subject"] = "Invoice payment and bank transfer"
    message["body_text"] = "Please arrange an invoice payment and bank transfer."
    sent = install_fake_gmail(monkeypatch, message=message)
    install_fake_ai(monkeypatch)
    gmail_assistant.configure_assistant(db, user.id, enabled=True, auto_send_enabled=True)

    result = asyncio.run(gmail_assistant.run_gmail_assistant_for_user(db, user.id, force=True))

    assert result["summary"]["replies_sent"] == 0
    assert sent == []
    assert gmail_assistant._load_record(db, user.id, "message-1")["status"] == "DRAFT_READY"
    db.close()


def test_gmail_assistant_pause_prevents_inbox_processing(monkeypatch):
    db, user = make_db()
    sent = install_fake_gmail(monkeypatch)
    install_fake_ai(monkeypatch)
    gmail_assistant.configure_assistant(db, user.id, enabled=False)

    result = asyncio.run(gmail_assistant.run_gmail_assistant_for_user(db, user.id, force=True))

    assert result["status"] == "PAUSED"
    assert sent == []
    assert db.query(Task).filter(Task.user_id == user.id).count() == 0
    db.close()



def test_followup_thread_polling_is_throttled_between_scheduler_cycles(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.connectors import gmail

    db, user = make_db()
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(gmail_assistant, "_now", lambda: now)
    record = {
        "message_id": "sent-message-1",
        "thread_id": "thread-1",
        "from": "colleague@example.com",
        "status": "SENT_WAITING_REPLY",
        "sent_at": (now - timedelta(days=1)).isoformat(),
        "follow_up_at": (now + timedelta(days=2)).isoformat(),
        "last_thread_check_at": (now - timedelta(minutes=5)).isoformat(),
    }
    gmail_assistant._save_record(db, user.id, record)

    async def unexpected_thread_fetch(*args, **kwargs):
        raise AssertionError("Gmail thread must not be fetched inside the 30-minute interval")

    monkeypatch.setattr(gmail, "get_thread", unexpected_thread_fetch)
    stats = asyncio.run(gmail_assistant._process_followups(db, user.id, False))

    assert stats["checked"] == 0
    assert stats["errors"] == 0
    db.close()


def test_followup_thread_poll_persists_attempt_before_network_request(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.connectors import gmail

    db, user = make_db()
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(gmail_assistant, "_now", lambda: now)
    record = {
        "message_id": "sent-message-2",
        "thread_id": "thread-2",
        "from": "colleague@example.com",
        "status": "SENT_WAITING_REPLY",
        "sent_at": (now - timedelta(days=1)).isoformat(),
        "follow_up_at": (now + timedelta(days=2)).isoformat(),
    }
    gmail_assistant._save_record(db, user.id, record)
    calls = []

    async def get_thread(db_arg, user_id, thread_id):
        calls.append(thread_id)
        return {"status": "COMPLETED", "id": thread_id, "messages": []}

    monkeypatch.setattr(gmail, "get_thread", get_thread)
    stats = asyncio.run(gmail_assistant._process_followups(db, user.id, False))

    saved = gmail_assistant._load_record(db, user.id, "sent-message-2")
    assert calls == ["thread-2"]
    assert stats["checked"] == 1
    assert saved["last_thread_check_at"] == now.isoformat().replace("+00:00", "Z")
    db.close()


def test_followup_error_is_classified_without_copying_provider_response_body():
    from app.gmail_assistant import _gmail_error_category

    error = RuntimeError("Gmail API request failed: HTTP 503 secret-user-message-body")
    assert _gmail_error_category(error) == "GOOGLE_UNAVAILABLE"
    assert _gmail_error_category(RuntimeError("invalid_grant")) == "REAUTH_REQUIRED"



def test_followup_failure_is_throttled_and_saved_as_safe_category(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.connectors import gmail

    db, user = make_db()
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(gmail_assistant, "_now", lambda: now)
    record = {
        "message_id": "sent-message-3",
        "thread_id": "thread-3",
        "from": "colleague@example.com",
        "status": "SENT_WAITING_REPLY",
        "sent_at": (now - timedelta(days=1)).isoformat(),
        "follow_up_at": (now + timedelta(days=2)).isoformat(),
    }
    gmail_assistant._save_record(db, user.id, record)
    calls = []

    async def fail_thread(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("Google token refresh failed temporarily: HTTP 503 (server_error).")

    monkeypatch.setattr(gmail, "get_thread", fail_thread)
    first = asyncio.run(gmail_assistant._process_followups(db, user.id, False))
    saved = gmail_assistant._load_record(db, user.id, "sent-message-3")
    second = asyncio.run(gmail_assistant._process_followups(db, user.id, False))

    assert first["errors"] == 1
    assert saved["last_gmail_error_category"] == "GOOGLE_UNAVAILABLE"
    assert second["errors"] == 0
    assert calls == [1]
    db.close()
