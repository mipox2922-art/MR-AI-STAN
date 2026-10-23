import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ActivityLog, ApprovalRequest, Execution, Task, TaskStep
from app.core.orchestrator import run


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_low_risk_system_mission_executes_and_records_verifiable_evidence(monkeypatch):
    import app.orchestration.executor as executor_module

    db = make_db()
    monkeypatch.setattr(
        executor_module,
        "system_status",
        lambda _user: {"runtime": "ONLINE", "verified": True},
    )

    result = asyncio.run(run(1, "system cpu ram", db))

    task = db.query(Task).one()
    approval_count = db.query(ApprovalRequest).count()
    execution = db.query(Execution).one()
    steps = db.query(TaskStep).filter_by(task_id=task.id).all()

    assert result["status"] == "COMPLETED"
    assert result["execution_started"] is True
    assert result["task_id"] == task.id
    assert task.status == "COMPLETED"
    assert task.approved_by == 1
    assert approval_count == 0
    assert execution.status == "COMPLETED"
    assert len(steps) == 1
    assert steps[0].state == "verified"
    assert '"verified": true' in (steps[0].evidence or "").lower()
    assert db.query(ActivityLog).filter_by(action="MISSION_COMPLETED").count() == 1
    db.close()
