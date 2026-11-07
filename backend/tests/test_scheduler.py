from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Notification, ScheduledJob, Setting, Task, User
from app.scheduler import run_chief_of_staff_cycle, run_due_jobs
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


def test_due_schedule_queues_an_owner_approved_orchestrator_mission():
    db = make_db()
    now = datetime(2026, 11, 6, 8, 0, 0)
    job = ScheduledJob(
        user_id=17,
        title="Daily owner briefing",
        command="Review 343Shop and Gmail",
        status="ACTIVE",
        run_at=now - timedelta(minutes=1),
        next_run_at=now - timedelta(minutes=1),
    )
    db.add(job)
    db.commit()

    assert run_due_jobs(db, now=now) == 1
    task = db.query(Task).one()
    assert task.agent == "orchestrator"
    assert task.source == "orchestrator"
    assert task.approved_by == 17
    assert task.description == "Review 343Shop and Gmail"
    db.close()



def test_chief_of_staff_starts_one_daily_self_initiated_moog_research_mission(monkeypatch):
    import asyncio
    from app import scheduler as scheduler_module

    db = make_db()
    user = User(username="owner", password_hash="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    calls = []

    async def fake_execute_mission(goal, owner, session):
        calls.append((goal, owner.id))
        mission = Task(
            user_id=owner.id,
            title="MOOG lead research",
            description=goal,
            status="COMPLETED",
            agent="orchestrator",
            source="orchestrator",
            requested_by="MR AI Orchestrator",
            approved_by=owner.id,
            progress=100,
        )
        session.add(mission)
        session.commit()
        session.refresh(mission)
        return {"status": "COMPLETED", "mission": {"id": mission.id, "status": mission.status}}

    monkeypatch.setattr(
        "app.orchestration.executor.execute_mission",
        fake_execute_mission,
    )
    first = asyncio.run(run_chief_of_staff_cycle(db))
    second = asyncio.run(run_chief_of_staff_cycle(db))

    assert first["users_checked"] == 1
    assert first["missions_started"] == 1
    assert first["missions_completed"] == 1
    assert second["missions_started"] == 0
    assert len(calls) == 1
    mission = db.query(Task).one()
    assert mission.requested_by == scheduler_module.CHIEF_OF_STAFF_REQUESTED_BY
    assert "MOOG Digital Printing & Branding" in mission.description
    assert db.query(Setting).filter(
        Setting.user_id == user.id,
        Setting.key == scheduler_module.CHIEF_OF_STAFF_CYCLE_KEY,
    ).count() == 1
    db.close()



def _create_waiting_chief_mission(db, user, updated_at, plan=None):
    import json
    from app.scheduler import CHIEF_OF_STAFF_GOAL, CHIEF_OF_STAFF_REQUESTED_BY

    packet = {} if plan is None else {"plan": plan, "steps": []}
    mission = Task(
        user_id=user.id,
        title="MOOG lead research",
        description=CHIEF_OF_STAFF_GOAL,
        status="WAITING_FOR_HAND",
        priority="NORMAL",
        agent="orchestrator",
        source="orchestrator",
        requested_by=CHIEF_OF_STAFF_REQUESTED_BY,
        approved_by=user.id,
        updated_at=updated_at,
        result=json.dumps(packet),
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def test_chief_of_staff_resumes_old_safe_research_mission_without_duplicate(monkeypatch):
    import asyncio
    import json
    from app.scheduler import CHIEF_OF_STAFF_GOAL, run_chief_of_staff_cycle

    db = make_db()
    user = User(username="retry-owner", password_hash="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    now = datetime.utcnow()
    plan = {"steps": [{"agent": "research", "tools": ["searxng"], "request": CHIEF_OF_STAFF_GOAL}]}
    mission = _create_waiting_chief_mission(db, user, now - timedelta(minutes=31), plan)
    calls = []

    async def fake_execute(goal, owner, session, mission=None):
        calls.append((goal, owner.id, mission.id))
        mission.status = "COMPLETED"
        mission.progress = 100
        mission.result = json.dumps({"plan": plan, "steps": [], "verified_steps": 1})
        session.commit()
        return {"status": "COMPLETED", "mission": {"id": mission.id}}

    monkeypatch.setattr("app.orchestration.executor.execute_mission", fake_execute)
    summary = asyncio.run(run_chief_of_staff_cycle(db))

    db.refresh(mission)
    assert calls == [(CHIEF_OF_STAFF_GOAL, user.id, mission.id)]
    assert summary["missions_resumed"] == 1
    assert summary["missions_completed"] == 1
    assert summary["missions_started"] == 0
    assert db.query(Task).filter_by(user_id=user.id, requested_by="MR AI Chief of Staff").count() == 1
    assert mission.status == "COMPLETED"
    db.close()


def test_chief_of_staff_does_not_retry_young_or_unsafe_mission(monkeypatch):
    import asyncio
    import json
    from app.scheduler import run_chief_of_staff_cycle, _chief_of_staff_retry_block_reason, _chief_of_staff_wait_diagnostics

    db = make_db()
    user = User(username="safe-retry-owner", password_hash="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    now = datetime.utcnow()
    mission = _create_waiting_chief_mission(
        db, user, now - timedelta(minutes=5),
        {"steps": [{"agent": "research", "tools": ["searxng"]}]},
    )
    calls = []

    async def fake_execute(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("A young mission must not be retried")

    monkeypatch.setattr("app.orchestration.executor.execute_mission", fake_execute)
    summary = asyncio.run(run_chief_of_staff_cycle(db))
    assert calls == []
    assert summary["missions_resumed"] == 0
    assert summary["missions_waiting"] == 1
    assert summary["missions_waiting_for_hand"] == 1
    assert _chief_of_staff_retry_block_reason(mission, now) == "cooldown_active"

    mission.updated_at = now - timedelta(minutes=31)
    mission.result = json.dumps({
        "plan": {"steps": [{"agent": "gmail", "tools": ["gmail"]}]},
        "steps": [],
    })
    db.commit()
    summary = asyncio.run(run_chief_of_staff_cycle(db))
    assert calls == []
    assert summary["missions_resumed"] == 0
    assert summary["missions_waiting"] == 1
    assert _chief_of_staff_retry_block_reason(mission, now) == "plan_contains_non_research_agent_or_missing_search_tool"
    planned_agents, executed_states = _chief_of_staff_wait_diagnostics(mission)
    assert planned_agents == "gmail:gmail"
    assert executed_states == "no_execution_steps"
    db.close()



def test_chief_of_staff_held_log_is_deduplicated(monkeypatch):
    import logging
    from app.scheduler import (
        _CHIEF_OF_STAFF_LAST_HELD_LOG,
        _log_chief_of_staff_held_mission,
        CHIEF_OF_STAFF_GOAL,
        CHIEF_OF_STAFF_REQUESTED_BY,
    )

    db = make_db()
    user = User(username="held-log-owner", password_hash="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    mission = _create_waiting_chief_mission(
        db, user, datetime.utcnow() - timedelta(minutes=5),
        {"steps": [{"agent": "gmail", "tools": ["gmail"]}]},
    )
    records = []

    class Capture:
        def warning(self, message, *args):
            records.append(message % args)

    _CHIEF_OF_STAFF_LAST_HELD_LOG.pop(mission.id, None)
    monkeypatch.setattr("app.scheduler.logger", Capture())
    now = datetime.utcnow()
    _log_chief_of_staff_held_mission(mission, "WAITING_FOR_HAND", now)
    _log_chief_of_staff_held_mission(mission, "WAITING_FOR_HAND", now)
    assert len(records) == 1
    assert "plan_contains_non_research_agent_or_missing_search_tool" in records[0]
    assert "gmail:gmail" in records[0]
    assert CHIEF_OF_STAFF_GOAL in mission.description
    assert CHIEF_OF_STAFF_REQUESTED_BY == mission.requested_by
    db.close()
