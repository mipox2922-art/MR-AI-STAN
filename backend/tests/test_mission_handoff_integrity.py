from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Task
from app.routers.agents import report_mission_handoff


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_client_handoff_cannot_mark_remote_action_verified_or_completed():
    db = make_db()
    mission = Task(
        user_id=7,
        title="Open a page",
        status="WAITING",
        progress=40,
        agent="orchestrator",
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)

    result = report_mission_handoff(
        mission.id,
        {"status": "COMPLETED", "evidence": {"verified": True, "url": "https://example.com"}},
        current_user=SimpleNamespace(id=7),
        db=db,
    )

    db.refresh(mission)
    assert result["status"] == "WAITING_FOR_VERIFICATION"
    assert result["verified"] is False
    assert mission.status == "WAITING_FOR_VERIFICATION"
    assert mission.progress < 100
    assert "cannot independently verify" in (mission.error or "")


def test_handoff_cannot_complete_an_arbitrary_regular_task():
    db = make_db()
    task = Task(
        user_id=7,
        title="Ordinary task",
        status="PENDING",
        progress=0,
        agent="scheduler",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    with pytest.raises(HTTPException) as exc:
        report_mission_handoff(
            task.id,
            {"status": "COMPLETED", "evidence": {"verified": True}},
            current_user=SimpleNamespace(id=7),
            db=db,
        )

    assert exc.value.status_code == 409
    db.refresh(task)
    assert task.status == "PENDING"
