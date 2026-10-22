import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Setting, Task, TaskStep
from app.routers import jobs


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def sample_result(query, limit=25):
    assert limit == 25
    return {
        "status": "COMPLETED",
        "query": query,
        "count": 1,
        "results": [{
            "id": "role-1",
            "title": "Remote Graphic Designer",
            "company": "Example Studio",
            "location": "Worldwide",
            "url": "https://jobs.example.test/role-1",
            "description": "Create graphic design assets and clear production layouts.",
            "tags": ["design", "creative"],
            "source": "Remotive",
        }],
        "sources": ["Remotive"],
        "source_warnings": [],
    }


def test_job_autopilot_runs_queries_and_records_a_waiting_profile_task(monkeypatch):
    db = make_db()

    async def fake_research(query, limit=25):
        return sample_result(query, limit)

    monkeypatch.setattr(jobs, "research_public_jobs", fake_research)

    result = asyncio.run(jobs.run_job_autopilot_for_user(db, 1, force=True))

    task = db.query(Task).one()
    steps = db.query(TaskStep).filter(TaskStep.task_id == task.id).order_by(TaskStep.position).all()
    packet = json.loads(task.result)

    assert result["status"] == "COMPLETED"
    assert result["candidate_count"] == 1
    assert result["new_jobs"] == 1
    assert result["drafts_ready"] == 0
    assert result["applications_submitted"] == 0
    assert task.source == "autopilot"
    assert task.agent == "jobs"
    assert task.status == "WAITING_FOR_PROFILE"
    assert packet["submission"]["status"] == "NOT_SUBMITTED"
    assert len(steps) == 2
    assert steps[0].state == "verified"
    assert steps[1].state == "pending"


def test_job_autopilot_deduplicates_the_same_public_listing(monkeypatch):
    db = make_db()

    async def fake_research(query, limit=25):
        return sample_result(query, limit)

    monkeypatch.setattr(jobs, "research_public_jobs", fake_research)

    first = asyncio.run(jobs.run_job_autopilot_for_user(db, 7, force=True))
    second = asyncio.run(jobs.run_job_autopilot_for_user(db, 7, force=True))

    assert first["new_jobs"] == 1
    assert second["new_jobs"] == 0
    assert db.query(Task).filter(Task.user_id == 7, Task.source == "autopilot").count() == 1


def test_job_autopilot_builds_a_cover_letter_only_from_saved_profile_facts(monkeypatch):
    db = make_db()
    profile = {
        "full_name": "Boss Ferisi",
        "email": "ferisi@example.com",
        "skills": ["graphic design", "printing"],
        "experience_summary": "I create print layouts and graphic assets for small projects.",
        "portfolio_url": "https://portfolio.example.com",
    }
    db.add(Setting(
        user_id=3,
        key=jobs.APPLICATION_PROFILE_KEY,
        value=json.dumps(profile),
    ))
    db.commit()

    async def fake_research(query, limit=25):
        return sample_result(query, limit)

    monkeypatch.setattr(jobs, "research_public_jobs", fake_research)

    result = asyncio.run(jobs.run_job_autopilot_for_user(db, 3, force=True))
    task = db.query(Task).one()
    packet = json.loads(task.result)

    assert result["drafts_ready"] == 1
    assert task.status == "READY_FOR_REVIEW"
    assert packet["application_draft"]["subject"] == "Application for Remote Graphic Designer"
    assert "graphic design, printing" in packet["application_draft"]["cover_letter"]
    assert "print layouts" in packet["application_draft"]["cover_letter"]
    assert packet["submission"]["status"] == "NOT_SUBMITTED"
    assert result["applications_submitted"] == 0


def test_saving_application_profile_refreshes_pending_autopilot_draft():
    db = make_db()
    task = Task(
        user_id=4,
        title="Application prep: Remote Graphic Designer",
        description="Company: Example Studio\nRole: Remote Graphic Designer\nJob URL: https://jobs.example.test/role-1",
        status="WAITING_FOR_PROFILE",
        priority="NORMAL",
        agent="jobs",
        source="autopilot",
        result=json.dumps({
            "workflow": "JOB_APPLICATION",
            "status": "WAITING_FOR_PROFILE",
            "job": sample_result("graphic designer")["results"][0],
            "application_draft": None,
            "submission": {"status": "NOT_SUBMITTED"},
        }),
    )
    db.add(task)
    db.flush()
    db.add(TaskStep(task_id=task.id, position=1, title="Found", state="verified", evidence="source url"))
    db.add(TaskStep(task_id=task.id, position=2, title="Prepare draft", state="pending", evidence="profile missing"))
    db.commit()

    profile = {
        "full_name": "Boss Ferisi",
        "email": "ferisi@example.com",
        "skills": ["graphic design"],
        "experience_summary": "I prepare clear design layouts.",
    }
    refreshed = jobs._refresh_waiting_application_drafts(db, 4, profile)
    db.commit()
    db.refresh(task)
    packet = json.loads(task.result)
    step = db.query(TaskStep).filter(TaskStep.task_id == task.id, TaskStep.position == 2).one()

    assert refreshed == 1
    assert task.status == "READY_FOR_REVIEW"
    assert packet["application_draft"]["cover_letter"]
    assert step.state == "pending"
    assert json.loads(step.evidence or "{}")["submitted"] is False
