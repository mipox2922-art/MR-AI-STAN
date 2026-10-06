from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User
from app.core.intent import classify
from app.core.permissions import check_permission
from app.core.gateway import execute


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_intent_engine_handles_mixed_language():
    intent = classify("tafuta taarifa za AI kwenye web")
    assert intent.name == "WEB_RESEARCH"
    assert intent.confidence > 0.5
    assert intent.executable is True


def test_high_risk_requires_approval():
    db = make_db()
    decision = check_permission(db, 1, "GMAIL_SEND", "HIGH")
    assert decision.allowed is False
    assert decision.requires_approval is True


def test_system_tool_returns_real_telemetry_shape():
    db = make_db()
    result = __import__("asyncio").run(execute(classify("system cpu ram"), 1, db))
    assert result["status"] == "COMPLETED"
    assert result["source"] == "psutil"
    assert "cpu_percent" in result["telemetry"]
    assert "memory_percent" in result["telemetry"]


def test_memory_save_is_persistent():
    db = make_db()
    intent = classify("kumbuka hii")
    result = __import__("asyncio").run(execute(intent, 1, db))
    assert result["status"] == "COMPLETED"
    assert db.query(__import__("app.models", fromlist=["Memory"]).Memory).count() == 1
