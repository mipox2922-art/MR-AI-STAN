import asyncio
import json
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Task, User
from app import scheduler
from app.orchestration import executor


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_dispatcher_runs_only_owner_approved_orchestrator_missions(monkeypatch):
    db = make_db()
    owner = User(username="boss-ferisi", password_hash="test-only")
    other = User(username="other-user", password_hash="test-only")
    db.add_all([owner, other])
    db.commit()
    db.refresh(owner)
    db.refresh(other)

    approved = Task(
        user_id=owner.id,
        title="Read-only approved mission",
        description="Check verified system status",
        status="PENDING",
        priority="NORMAL",
        agent="orchestrator",
        source="orchestrator",
        requested_by="Boss Ferisi",
        approved_by=owner.id,
        approved_at=datetime.utcnow(),
    )
    unapproved = Task(
        user_id=other.id,
        title="Mission without owner approval",
        description="Do not execute until approved",
        status="PENDING",
        priority="NORMAL",
        agent="orchestrator",
        source="orchestrator",
        requested_by="MR AI Orchestrator",
        approved_by=None,
    )
    db.add_all([approved, unapproved])
    db.commit()
    db.refresh(approved)
    db.refresh(unapproved)

    calls = []

    async def fake_execute_mission(request, user, session, mission=None):
        calls.append({"request": request, "user_id": user.id, "mission_id": mission.id, "status_at_start": mission.status})
        mission.status = "COMPLETED"
        mission.result = json.dumps({"status": "COMPLETED", "verified_steps": 1})
        mission.progress = 100
        mission.updated_at = datetime.utcnow()
        session.commit()
        return {"status": "COMPLETED", "mission": {"id": mission.id}}

    monkeypatch.setattr(executor, "execute_mission", fake_execute_mission)

    processed = asyncio.run(scheduler.run_approved_pending_missions(db, limit=3))

    assert processed == 1
    assert calls == [{
        "request": "Check verified system status",
        "user_id": owner.id,
        "mission_id": approved.id,
        "status_at_start": "RUNNING",
    }]
    db.refresh(approved)
    db.refresh(unapproved)
    assert approved.status == "COMPLETED"
    assert unapproved.status == "PENDING"
    db.close()
