from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Task
from app.task_runner import run_pending_tasks


def test_scheduler_retries_task_left_running_by_dead_worker():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    task = Task(
        user_id=1,
        title="[SCHEDULED] Recover system task",
        description="system cpu ram",
        status="RUNNING",
        priority="NORMAL",
        agent="scheduler",
        updated_at=datetime.utcnow() - timedelta(minutes=30),
    )
    db.add(task)
    db.commit()

    import asyncio
    processed = asyncio.run(run_pending_tasks(db))

    db.refresh(task)
    assert processed == 1
    assert task.status == "COMPLETED"
    assert task.progress == 100
