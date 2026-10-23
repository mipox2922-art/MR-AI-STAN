import asyncio
import json
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ApprovalRequest, Memory, Task, TaskStep
from app.orchestration.executor import execute_mission


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_connected_gmail_read_executes_real_read_only_connector(monkeypatch):
    import app.connectors.gmail as gmail_module

    db = make_db()
    user = SimpleNamespace(id=41)
    calls = {}

    monkeypatch.setattr(gmail_module, "connection_status", lambda _db, _user_id: {"connected": True})

    async def fake_list_messages(_db, user_id, query="", max_results=20):
        calls.update(user_id=user_id, query=query, max_results=max_results)
        return {
            "status": "COMPLETED",
            "result_size_estimate": 1,
            "messages": [{
                "id": "message-1",
                "subject": "Interview invitation",
                "from": "recruiter@example.test",
                "snippet": "Please share your availability.",
            }],
        }

    monkeypatch.setattr(gmail_module, "list_messages", fake_list_messages)

    result = asyncio.run(execute_mission("Soma email zangu za leo", user, db))

    task = db.query(Task).one()
    step = db.query(TaskStep).filter_by(task_id=task.id).one()
    packet = json.loads(task.result)

    assert result["status"] == "COMPLETED"
    assert task.status == "COMPLETED"
    assert task.approved_by == user.id
    assert calls == {"user_id": user.id, "query": "in:inbox newer_than:1d", "max_results": 20}
    assert step.state == "verified"
    assert packet["verified_steps"] == 1
    assert packet["steps"][0]["tool"] == "gmail"
    assert packet["steps"][0]["evidence"]["messages"][0]["id"] == "message-1"
    assert db.query(ApprovalRequest).count() == 0
    db.close()


def test_gmail_not_connected_waits_for_approval_without_claiming_execution(monkeypatch):
    import app.connectors.gmail as gmail_module

    db = make_db()
    user = SimpleNamespace(id=42)
    monkeypatch.setattr(gmail_module, "connection_status", lambda _db, _user_id: {"connected": False})

    async def should_not_read(*_args, **_kwargs):
        raise AssertionError("Gmail API must not be called when OAuth is disconnected")

    monkeypatch.setattr(gmail_module, "list_messages", should_not_read)

    result = asyncio.run(execute_mission("Soma email zangu", user, db))

    task = db.query(Task).one()
    assert result["status"] == "WAITING_APPROVAL"
    assert task.status == "WAITING_APPROVAL"
    assert task.approved_by is None
    assert db.query(ApprovalRequest).count() == 1
    assert db.query(TaskStep).filter_by(task_id=task.id).count() == 1
    assert db.query(TaskStep).filter_by(task_id=task.id).one().state == "pending"
    db.close()


def test_memory_save_executes_against_persistent_database():
    db = make_db()
    user = SimpleNamespace(id=43)

    result = asyncio.run(execute_mission(
        "Kumbuka hii: napenda kazi za graphic design na printing",
        user,
        db,
    ))

    task = db.query(Task).one()
    memory = db.query(Memory).filter_by(user_id=user.id).one()
    step = db.query(TaskStep).filter_by(task_id=task.id).one()

    assert result["status"] == "COMPLETED"
    assert task.status == "COMPLETED"
    assert memory.value == "napenda kazi za graphic design na printing"
    assert step.state == "verified"
    assert db.query(ApprovalRequest).count() == 0
    db.close()


def test_resume_skips_already_verified_job_step(monkeypatch):
    import app.connectors.gmail as gmail_module
    import app.routers.jobs as jobs_module

    db = make_db()
    user = SimpleNamespace(id=44)
    request = "Tafuta kazi na soma email zangu"
    task = Task(
        user_id=user.id,
        title=request,
        description=request,
        status="WAITING_FOR_HAND",
        priority="NORMAL",
        agent="orchestrator",
        source="orchestrator",
        approved_by=user.id,
        progress=50,
    )
    db.add(task)
    db.flush()

    completed_job_step = {
        "step": 1,
        "agent": "jobs",
        "name": "Job Research Agent",
        "tool": "public_job_feeds",
        "status": "COMPLETED",
        "verified": True,
        "evidence": {"query": "remote jobs", "count": 1, "results": []},
    }
    db.add(TaskStep(
        task_id=task.id,
        position=1,
        title="Job Research Agent",
        state="verified",
        evidence=json.dumps({
            "task_id": task.id,
            "agent": "jobs",
            "tool": "public_job_feeds",
            "execution_status": "COMPLETED",
            "verified": True,
            "output": completed_job_step["evidence"],
            "step_result": completed_job_step,
        }),
    ))
    db.add(TaskStep(
        task_id=task.id,
        position=2,
        title="Gmail Agent",
        state="pending",
        evidence=None,
    ))
    db.commit()
    db.refresh(task)

    async def should_not_search(*_args, **_kwargs):
        raise AssertionError("Verified job search must not be repeated on resume")

    monkeypatch.setattr(jobs_module, "research_public_jobs", should_not_search)
    monkeypatch.setattr(gmail_module, "connection_status", lambda _db, _user_id: {"connected": True})

    async def fake_list_messages(_db, user_id, query="", max_results=20):
        return {
            "status": "COMPLETED",
            "result_size_estimate": 0,
            "messages": [],
        }

    monkeypatch.setattr(gmail_module, "list_messages", fake_list_messages)

    result = asyncio.run(execute_mission(request, user, db, mission=task))

    db.refresh(task)
    rows = db.query(TaskStep).filter_by(task_id=task.id).order_by(TaskStep.position).all()
    packet = json.loads(task.result)

    assert result["status"] == "COMPLETED"
    assert task.status == "COMPLETED"
    assert [row.state for row in rows] == ["verified", "verified"]
    assert packet["verified_steps"] == 2
    assert packet["total_steps"] == 2
    assert packet["steps"][0]["tool"] == "public_job_feeds"
    assert packet["steps"][1]["tool"] == "gmail"
    db.close()
