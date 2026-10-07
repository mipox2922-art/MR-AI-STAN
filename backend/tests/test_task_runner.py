from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ApprovalRequest, Task
from app.task_runner import run_pending_tasks


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_scheduler_worker_executes_safe_system_task():
    db = make_db()
    task = Task(
        user_id=1,
        title="[SCHEDULED] Check system",
        description="system cpu ram",
        status="PENDING",
        priority="NORMAL",
        agent="scheduler",
    )
    db.add(task)
    db.commit()

    processed = __import__("asyncio").run(run_pending_tasks(db))

    assert processed == 1
    refreshed = db.query(Task).one()
    assert refreshed.status == "COMPLETED"
    assert refreshed.progress == 100
    assert "telemetry" in (refreshed.result or "")


def test_scheduler_worker_does_not_process_manual_tasks():
    db = make_db()
    db.add(
        Task(
            user_id=1,
            title="Manual task",
            description="system cpu ram",
            status="PENDING",
            priority="NORMAL",
            agent=None,
        )
    )
    db.commit()

    processed = __import__("asyncio").run(run_pending_tasks(db))

    assert processed == 0
    assert db.query(Task).one().status == "PENDING"


def test_scheduler_worker_creates_approval_for_high_risk_task():

    db = make_db()
    task = Task(
        user_id=1,
        title="[SCHEDULED] Shutdown",
        description="shutdown",
        status="PENDING",
        priority="NORMAL",
        agent="scheduler",
    )
    db.add(task)
    db.commit()

    processed = __import__("asyncio").run(run_pending_tasks(db))

    assert processed == 1
    refreshed = db.query(Task).one()
    assert refreshed.status == "WAITING_APPROVAL"
    approval = db.query(ApprovalRequest).one()
    assert approval.status == "PENDING"
    assert '"task_id": 1' in approval.payload


def test_high_risk_external_action_requires_approval_before_hand():
    db = make_db()
    task = Task(
        user_id=1,
        title="[SCHEDULED] Send email",
        description="send email",
        status="PENDING",
        priority="NORMAL",
        agent="scheduler",
    )
    db.add(task)
    db.commit()

    processed = __import__("asyncio").run(run_pending_tasks(db))

    assert processed == 1
    refreshed = db.query(Task).one()
    assert refreshed.status == "WAITING_APPROVAL"
    assert db.query(ApprovalRequest).count() == 1
