import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ActivityLog, ApprovalRequest, Execution, Task, TaskStep
from app.core.orchestrator import run


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_even_low_risk_orchestrator_task_waits_for_boss_approval():
    db = make_db()
    result = asyncio.run(run(1, "system cpu ram", db))

    assert result["status"] == "WAITING_APPROVAL"
    assert result["execution_started"] is False
    assert result["task_id"]
    assert result["approval_id"]
    task = db.query(Task).one()
    approval = db.query(ApprovalRequest).one()
    execution = db.query(Execution).one()
    assert task.status == "WAITING_APPROVAL"
    assert task.source == "orchestrator"
    assert task.requested_by == "MR AI Orchestrator"
    assert approval.status == "PENDING"
    assert '"task_id":' in approval.payload
    assert execution.status == "WAITING_APPROVAL"
    steps = db.query(TaskStep).filter_by(task_id=task.id).all()
    assert steps
    assert all(step.state == "pending" and not step.evidence for step in steps)
    assert db.query(ActivityLog).filter_by(action="ORCHESTRATION_PROPOSED").count() == 1
    db.close()
