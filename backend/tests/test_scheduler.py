from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Notification, ScheduledJob, Task
from app.scheduler import run_due_jobs
from app.routers.scheduler import run_schedule_now


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_one_shot_schedule_creates_task_and_notification():
    db = make_db()
    now = datetime(2026, 10, 7, 12, 0, 0)

    job = ScheduledJob(
        user_id=1,
        title="Daily briefing",
        command="prepare briefing",
        status="ACTIVE",
        run_at=now - timedelta(minutes=1),
        next_run_at=now - timedelta(minutes=1),
    )
    db.add(job)
    db.commit()

    fired = run_due_jobs(db, now=now)

    assert fired == 1
    assert db.query(Task).count() == 1
    assert db.query(Notification).count() == 1

    refreshed = db.query(ScheduledJob).one()
    assert refreshed.status == "COMPLETED"
    assert refreshed.next_run_at is None
    assert refreshed.last_run_at == now


def test_recurring_schedule_advances_to_next_future_run():
    db = make_db()
    now = datetime(2026, 10, 7, 12, 0, 0)

    job = ScheduledJob(
        user_id=1,
        title="Hourly check",
        command="check system",
        status="ACTIVE",
        run_at=now - timedelta(hours=3),
        interval_minutes=60,
        next_run_at=now - timedelta(hours=3),
    )
    db.add(job)
    db.commit()

    fired = run_due_jobs(db, now=now)

    assert fired == 1
    refreshed = db.query(ScheduledJob).one()
    assert refreshed.status == "ACTIVE"
    assert refreshed.next_run_at == now + timedelta(hours=1)
    assert refreshed.last_run_at == now



def test_run_schedule_now_moves_next_run_to_now():
    db = make_db()
    now = datetime.utcnow()
    job = ScheduledJob(
        user_id=7,
        title="Immediate briefing",
        command="prepare briefing",
        status="PAUSED",
        run_at=now + timedelta(hours=1),
        next_run_at=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    result = run_schedule_now(job.id, type("User", (), {"id": 7})(), db)

    assert result["status"] == "ACTIVE"
    assert result["next_run_at"] is not None
    refreshed = db.query(ScheduledJob).one()
    assert refreshed.status == "ACTIVE"


def test_overlapping_scheduler_cycle_is_skipped(monkeypatch):
    import asyncio
    from app import scheduler as scheduler_module

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def blocked_cycle():
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return 2, 3

        monkeypatch.setattr(scheduler_module, "_run_scheduler_cycle_once", blocked_cycle)
        first = asyncio.create_task(scheduler_module.run_scheduler_cycle())
        await asyncio.wait_for(entered.wait(), timeout=1)

        # A simultaneous caller (for example the GitHub wake-up while the
        # in-process loop is running) must not start a second task scan.
        second = await scheduler_module.run_scheduler_cycle()
        assert second == (0, 0)

        release.set()
        assert await first == (2, 3)
        assert calls == 1

    asyncio.run(scenario())
