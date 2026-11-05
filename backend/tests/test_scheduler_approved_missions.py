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



def test_coding_ci_verification_updates_child_and_parent_mission(monkeypatch):
    from app.models import ActivityLog, TaskStep

    db = make_db()
    owner = User(username="coding-owner", password_hash="test-only")
    db.add(owner)
    db.commit()
    db.refresh(owner)

    parent = Task(
        user_id=owner.id,
        title="Fix backend bug",
        description="Fix bug in backend repository",
        status="WAITING_FOR_VERIFICATION",
        priority="NORMAL",
        agent="orchestrator",
        source="orchestrator",
        approved_by=owner.id,
        progress=0,
        result=json.dumps({
            "steps": [{
                "step": 1,
                "agent": "coding",
                "name": "Coding Agent",
                "status": "WAITING_FOR_VERIFICATION",
                "verified": False,
                "evidence": {"coding_task_id": 0},
            }],
            "verified_steps": 0,
            "total_steps": 1,
            "owner_approved": True,
            "memory_context": [],
        }),
    )
    db.add(parent)
    db.flush()
    child = Task(
        user_id=owner.id,
        title="Coding Agent: Fix backend bug",
        description="Fix bug in backend repository",
        status="IN_PROGRESS",
        priority="NORMAL",
        agent="coding",
        source="coding_agent",
        requested_by=f"mission:{parent.id}:1",
        approved_by=owner.id,
        progress=35,
        result=json.dumps({
            "commit_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "branch": "mr-ai/coding-agent/plan-2",
            "pull_request": {"url": "https://github.com/owner/repo/pull/11"},
            "mission_id": parent.id,
            "mission_step_position": 1,
        }),
    )
    db.add(child)
    db.flush()
    db.add(TaskStep(task_id=parent.id, position=1, title="Coding Agent", state="pending"))
    db.add(TaskStep(task_id=child.id, position=1, title="Verify CI", state="pending"))
    db.commit()

    async def fake_checks(commit_sha):
        assert commit_sha == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        return {"status": "PASSED", "checks": [{"name": "backend", "conclusion": "success"}]}

    monkeypatch.setattr("app.connectors.coding_workspace.get_commit_checks", fake_checks)
    processed = asyncio.run(scheduler.run_pending_coding_verifications(db))

    db.refresh(parent)
    db.refresh(child)
    parent_step = db.query(TaskStep).filter_by(task_id=parent.id).one()
    assert processed == 1
    assert child.status == "COMPLETED"
    assert child.progress == 100
    assert parent.status == "COMPLETED"
    assert parent.progress == 100
    assert parent_step.state == "verified"
    assert json.loads(parent.result)["steps"][0]["status"] == "COMPLETED"
    assert db.query(ActivityLog).filter_by(action="MISSION_CODING_CI_VERIFIED").count() == 1
    db.close()
