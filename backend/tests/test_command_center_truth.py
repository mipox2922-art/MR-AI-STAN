from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import ApprovalRequest, Task, TaskStep
from app.orchestration.briefing import build_executive_briefing
from app.routers import tasks as task_router
from app.routers import agents as agents_router
from app.orchestration.executor import execute_mission


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_progress_is_only_verified_steps_with_nonempty_evidence():
    db = make_db()
    assert task_router.progress_of([]) == 0
    task = Task(user_id=1, title="Audit project", agent="orchestrator", status="WAITING")
    db.add(task)
    db.flush()
    no_evidence = TaskStep(task_id=task.id, position=1, title="Read repository", state="verified", evidence=" ")
    failed = TaskStep(task_id=task.id, position=2, title="Run tests", state="failed", evidence="pytest failed")
    db.add_all([no_evidence, failed])
    db.commit()
    steps = task_router._steps_for(db, task.id)
    assert task_router.progress_of(steps) == 0
    assert task_router.can_mark_done(steps) is False
    no_evidence.evidence = "Commit 123abc; backend tests passed"
    no_evidence.state = "verified"
    db.commit()
    assert task_router.progress_of(task_router._steps_for(db, task.id)) == 50
    assert task_router.can_mark_done(task_router._steps_for(db, task.id)) is False


def test_task_cannot_be_completed_with_zero_steps_or_missing_evidence():
    db = make_db()
    task = Task(user_id=1, title="Historical task", agent="scheduler", status="COMPLETED", progress=100)
    db.add(task)
    db.flush()
    payload = task_router.task_payload(db, task)
    assert payload["status"] == "WAITING_FOR_VERIFICATION"
    assert payload["progress"] == 0
    step = TaskStep(task_id=task.id, position=1, title="Run operation", state="verified", evidence=None)
    db.add(step)
    db.commit()
    payload = task_router.task_payload(db, task)
    assert payload["status"] == "WAITING_FOR_VERIFICATION"
    assert payload["progress"] == 0


def test_orchestrator_mission_starts_as_approval_proposal_and_runs_nothing():
    db = make_db()
    user = SimpleNamespace(id=1)
    import asyncio
    result = asyncio.run(execute_mission("open browser and submit form", user, db))
    task = db.query(Task).one()
    approval = db.query(ApprovalRequest).one()
    assert result["status"] == "WAITING_APPROVAL"
    assert task.status == "WAITING_APPROVAL"
    assert task.source == "orchestrator"
    assert task.approved_by is None
    assert approval.status == "PENDING"
    assert db.query(TaskStep).filter_by(task_id=task.id).count() >= 1
    assert all(step.state == "pending" and not step.evidence for step in db.query(TaskStep).filter_by(task_id=task.id).all())


def test_agent_proposal_is_waiting_approval():
    db = make_db()
    app = FastAPI()
    app.include_router(agents_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    client = TestClient(app)
    response = client.post("/agents/execute", json={
        "action": "create_task", "title": "Review security posture", "agent": "security"
    })
    assert response.status_code == 200
    payload = response.json()
    task = db.query(Task).one()
    assert payload["status"] == "WAITING_APPROVAL"
    assert task.status == "WAITING_APPROVAL"
    assert task.source == "agent"
    assert task.approved_by is None
    assert db.query(ApprovalRequest).one().status == "PENDING"


def test_briefing_uses_database_counts_and_does_not_call_empty_registry_busy():
    db = make_db()
    user = SimpleNamespace(id=1)
    db.add_all([
        Task(user_id=1, title="Waiting approval", agent="security", status="WAITING_APPROVAL", source="agent"),
        Task(user_id=1, title="Failed task", agent="jobs", status="FAILED", error="source unavailable", source="agent"),
    ])
    db.commit()
    report = build_executive_briefing(user, db)
    assert report["tasks"]["total"] == 2
    assert report["tasks"]["failed"] == 1
    assert report["tasks"]["waiting"] == 1
    assert report["tasks"]["pending_approval"][0]["title"] == "Waiting approval"
    security_agent = next(item for item in report["agents"]["fleet"] if item["id"] == "security")
    assert security_agent["status"] == "WAITING"
    assert security_agent["current_task"]["status"] == "WAITING_APPROVAL"
    assert report["timezone"] == "Africa/Dar_es_Salaam"
