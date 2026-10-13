import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models import ActivityLog, Notification, Setting, User
from app.self_audit import AUDIT_KEY, run_self_audit


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def reset_provider_config(monkeypatch):
    for name in (
        "openrouter_api_key",
        "gemini_api_key",
        "kimi_api_key",
        "mistral_api_key",
        "xai_api_key",
    ):
        monkeypatch.setattr(settings, name, "", raising=False)
    monkeypatch.setattr(settings, "scheduler_enabled", True, raising=False)
    monkeypatch.setattr(settings, "serverless_mode", False, raising=False)


def test_self_audit_records_missing_ai_provider_and_notifies_once(monkeypatch):
    reset_provider_config(monkeypatch)
    db = make_db()
    db.add(User(username="boss", password_hash="test-hash"))
    db.commit()

    first = run_self_audit(db)
    assert first["status"] == "DEGRADED"
    assert first["checked_users"] == 1
    assert db.query(Notification).count() == 1
    assert db.query(ActivityLog).filter_by(action="SYSTEM_SELF_AUDIT").count() == 1

    second = run_self_audit(db)
    assert second["status"] == "DEGRADED"
    assert db.query(Notification).count() == 1
    assert db.query(ActivityLog).filter_by(action="SYSTEM_SELF_AUDIT").count() == 1

    stored = db.query(Setting).filter_by(key=AUDIT_KEY).one()
    report = json.loads(stored.value)
    assert report["status"] == "DEGRADED"
    assert any(item["id"] == "ai_provider" for item in report["blockers"])


def test_self_audit_notifies_when_provider_configuration_recovers(monkeypatch):
    reset_provider_config(monkeypatch)
    db = make_db()
    db.add(User(username="boss", password_hash="test-hash"))
    db.commit()

    run_self_audit(db)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-placeholder", raising=False)

    result = run_self_audit(db)
    assert result["status"] == "OPERATIONAL"
    notifications = db.query(Notification).order_by(Notification.id.asc()).all()
    assert len(notifications) == 2
    assert notifications[-1].title == "MR AI self-check recovered"
    assert db.query(ActivityLog).filter_by(action="SYSTEM_SELF_AUDIT").count() == 2
