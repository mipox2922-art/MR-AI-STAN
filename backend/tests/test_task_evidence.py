from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Task, TaskStep
from app.routers.tasks import can_mark_done, progress_of, step_is_verified, task_payload


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_no_steps_means_zero_progress_and_cannot_be_done():
    assert progress_of([]) == 0
    assert can_mark_done([]) is False


def test_verified_step_needs_nonempty_evidence():
    missing = TaskStep(task_id=1, position=1, title="Inspect code", state="verified", evidence="  ")
    verified = TaskStep(task_id=1, position=2, title="Build passed", state="verified", evidence="CI run 123 passed")
    assert not step_is_verified(missing)
    assert step_is_verified(verified)
    assert progress_of([missing, verified]) == 50
    assert can_mark_done([missing, verified]) is False


def test_task_payload_downgrades_legacy_completed_without_evidence():
    db = make_db()
    task = Task(user_id=1, title="Legacy task", status="COMPLETED", progress=100, agent="orchestrator")
    db.add(task)
    db.commit()
    db.refresh(task)

    payload = task_payload(db, task)
    assert payload["status"] == "WAITING_FOR_VERIFICATION"
    assert payload["progress"] == 0
    assert payload["verified_steps"] == 0
    assert payload["step_count"] == 0
    db.close()


def test_all_steps_need_evidence_before_completion():
    db = make_db()
    task = Task(user_id=1, title="Evidence task", status="IN_PROGRESS", agent="orchestrator")
    db.add(task)
    db.flush()
    db.add_all([
        TaskStep(task_id=task.id, position=1, title="Source found", state="verified", evidence="https://example.com/result", verified_at=datetime.utcnow()),
        TaskStep(task_id=task.id, position=2, title="Result checked", state="verified", evidence="CI run 123, job passed", verified_at=datetime.utcnow()),
    ])
    db.commit()
    db.refresh(task)

    payload = task_payload(db, task)
    assert payload["progress"] == 100
    assert payload["verified_steps"] == 2
    assert payload["step_count"] == 2
    assert can_mark_done(db.query(TaskStep).filter_by(task_id=task.id).all())
    db.close()
