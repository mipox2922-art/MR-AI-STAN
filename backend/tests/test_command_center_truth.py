from datetime import datetime, timedelta
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import ApprovalRequest, Execution, Task, TaskStep
from app.orchestration.briefing import build_executive_briefing
from app.routers import tasks as task_router
from app.routers import agents as agents_router
from app.orchestration.executor import execute_mission
from app.core.intent import classify
from app.core.orchestrator import run as run_orchestration


def make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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


def test_safe_system_status_mission_runs_without_manual_approval(monkeypatch):
    import asyncio
    import app.orchestration.executor as executor_module

    db = make_db()
    user = SimpleNamespace(id=1)
    monkeypatch.setattr(
        executor_module,
        "system_status",
        lambda _user: {"runtime": "ONLINE", "verified": True},
    )

    result = asyncio.run(execute_mission("system status", user, db))

    task = db.query(Task).one()
    assert result["status"] == "COMPLETED"
    assert task.status == "COMPLETED"
    assert task.approved_by == user.id
    assert db.query(ApprovalRequest).count() == 0
    step = db.query(TaskStep).one()
    assert step.state == "verified"
    assert "verified" in (step.evidence or "").lower() or "ONLINE" in (step.evidence or "")


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

def test_swahi_job_command_routes_to_job_research_not_generic_web_research():
    intent = classify("TAFUTA KAZI SAWA FANYA")
    assert intent.name == "JOB_RESEARCH"
    assert intent.risk == "LOW"
    assert intent.executable is True


def test_public_job_research_executes_and_records_verified_evidence(monkeypatch):
    import asyncio
    import app.routers.jobs as jobs_module

    db = make_db()
    user = SimpleNamespace(id=1)

    calls = {}

    async def fake_research(query, limit=25):
        calls.update(query=query, limit=limit)
        return {
            "status": "COMPLETED",
            "query": query,
            "count": 1,
            "results": [{
                "title": "Remote Graphic Designer",
                "company": "Example Studio",
                "location": "Worldwide",
                "url": "https://jobs.example.test/graphic-designer",
                "source": "Remotive",
            }],
            "sources": ["RemoteOK", "Remotive"],
            "source_warnings": [],
            "note": "Public job feeds only.",
        }

    monkeypatch.setattr(jobs_module, "research_public_jobs", fake_research)
    result = asyncio.run(run_orchestration(1, "TAFUTA KAZI SAWA FANYA", db))

    assert calls == {"query": "remote jobs", "limit": 15}, result
    task = db.query(Task).one()
    step = db.query(TaskStep).one()
    assert result["status"] == "COMPLETED"
    assert result["job_results"]["count"] == 1
    assert task.status == "COMPLETED"
    assert task.progress == 100
    assert task.agent == "jobs"
    assert step.state == "verified"
    assert "graphic-designer" in (step.evidence or "")
    assert db.query(ApprovalRequest).count() == 0

def test_repeated_job_search_resumes_exact_old_approval_task(monkeypatch):
    import asyncio
    import app.routers.jobs as jobs_module

    db = make_db()
    user = SimpleNamespace(id=1)
    request = "TAFUTA KAZI SAWA FANYA"
    task = Task(
        user_id=1, title=request, description=request, status="WAITING_APPROVAL",
        priority="NORMAL", agent="orchestrator", source="orchestrator",
        requested_by="MR AI Orchestrator", progress=0,
    )
    db.add(task)
    db.flush()
    execution = Execution(
        user_id=1, intent="WEB_RESEARCH", status="WAITING_APPROVAL", risk="LOW",
        result='{"task_id": ' + str(task.id) + ', "approval_id": 1, "status": "WAITING_APPROVAL"}',
    )
    db.add(execution)
    approval = ApprovalRequest(
        user_id=1, action="WEB_RESEARCH",
        payload=json.dumps({"task_id": task.id, "execution_id": 1, "intent": "WEB_RESEARCH"}),
        status="PENDING",
    )
    db.add(approval)
    db.add(TaskStep(task_id=task.id, position=1, title="Old web research step", state="pending"))
    db.commit()

    async def fake_research(query, limit=25):
        return {
            "status": "COMPLETED", "query": query, "count": 1,
            "results": [{
                "title": "Remote Designer", "company": "Example",
                "location": "Worldwide", "url": "https://jobs.example.test/one",
            }],
            "sources": ["RemoteOK"], "source_warnings": [],
        }

    monkeypatch.setattr(jobs_module, "research_public_jobs", fake_research)
    result = asyncio.run(run_orchestration(1, request, db))

    db.refresh(task)
    db.refresh(approval)
    db.refresh(execution)
    assert result["status"] == "COMPLETED"
    assert result["task_id"] == task.id
    assert db.query(Task).count() == 1
    assert task.agent == "jobs"
    assert task.status == "COMPLETED"
    assert approval.status == "CANCELLED"
    assert execution.intent == "JOB_RESEARCH"
    assert execution.status == "COMPLETED"
    assert db.query(TaskStep).filter_by(task_id=task.id).one().state == "verified"



def test_agent_fleet_reports_missing_execution_hands_instead_of_fake_ready_status():
    db = make_db()
    user = SimpleNamespace(id=99)

    report = build_executive_briefing(user, db)
    fleet = {agent["id"]: agent for agent in report["agents"]["fleet"]}

    assert report["agents"]["total"] == 11
    assert fleet["orchestrator"]["runtime_status"] == "READY"
    assert fleet["jobs"]["runtime_status"] == "READY"
    assert fleet["memory"]["runtime_status"] == "READY"
    for agent_id in ("browser", "coding", "creative", "device", "security"):
        assert fleet[agent_id]["runtime_status"] == "WAITING_FOR_HAND"
    assert fleet["gmail"]["runtime_status"] in {"NOT_CONNECTED", "NOT_CONFIGURED"}
    assert fleet["research"]["runtime_status"] in {"CONFIGURED", "NOT_CONNECTED", "AVAILABLE"}
    assert all("runtime_status" in item for item in fleet.values())
    db.close()
