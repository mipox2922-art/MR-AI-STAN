from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Task, TaskStep
from app.orchestration import briefing


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_executive_briefing_counts_every_runtime_task_state_consistently(monkeypatch):
    db = make_db()
    user = SimpleNamespace(id=44)
    fixtures = [
        ("Coding execution one", "HAND_EXECUTING", "coding"),
        ("Coding execution two", "EXECUTING", "coding"),
        ("Browser execution", "IN_PROGRESS", "browser"),
        ("Queued job", "QUEUED", "jobs"),
        ("Needs approval", "NEEDS_APPROVAL", "orchestrator"),
        ("Profile missing", "WAITING_FOR_PROFILE", "jobs"),
        ("Ready for review", "READY_FOR_REVIEW", "jobs"),
        ("Research failed", "ERROR", "research"),
        ("Verified task", "COMPLETED", "memory"),
    ]
    created = {}
    for title, status, agent in fixtures:
        task = Task(
            user_id=user.id,
            title=title,
            status=status,
            agent=agent,
            source="test",
        )
        db.add(task)
        db.flush()
        created[title] = task

    db.add(TaskStep(
        task_id=created["Verified task"].id,
        position=1,
        title="Evidence recorded",
        state="verified",
        evidence="Test evidence: verified output",
    ))
    db.commit()

    monkeypatch.setattr(
        briefing,
        "registry_summary",
        lambda: {"tools": [], "not_connected": 0, "optional": 0},
    )
    monkeypatch.setattr(
        briefing,
        "system_status",
        lambda _user: {"telemetry": {}, "services": {}},
    )
    monkeypatch.setattr(
        briefing,
        "_agent_runtime_status",
        lambda _agent_id, _user, _db, _tool_status: "READY",
    )

    result = briefing.build_executive_briefing(user, db)

    assert result["tasks"]["total"] == 9
    assert result["tasks"]["working"] == 3
    assert result["tasks"]["waiting"] == 4
    assert result["tasks"]["failed"] == 1
    assert result["tasks"]["completed"] == 1
    assert result["agents"]["working"] == 2

    coding = next(agent for agent in result["agents"]["fleet"] if agent["id"] == "coding")
    assert coding["status"] == "WORKING"
    db.close()
