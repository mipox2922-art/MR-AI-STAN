import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Memory, Setting, Task, TaskStep
from types import SimpleNamespace
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

def test_job_autopilot_retries_source_outage_after_short_backoff(monkeypatch):
    db = make_db()
    calls = 0

    async def failing_research(query, limit=25):
        nonlocal calls
        calls += 1
        raise RuntimeError("public feed offline")

    monkeypatch.setattr(jobs, "research_public_jobs", failing_research)

    first = asyncio.run(jobs.run_job_autopilot_for_user(db, 11, force=True))
    second = asyncio.run(jobs.run_job_autopilot_for_user(db, 11, force=False))
    setting = db.query(Setting).filter_by(user_id=11, key=jobs.AUTOPILOT_CONFIG_KEY).one()

    assert first["status"] == "SOURCE_ERROR"
    assert first["retry_after_minutes"] == 30
    assert second["status"] == "NOT_DUE"
    assert calls == 4
    stored = json.loads(setting.value)
    assert stored["last_run_status"] == "SOURCE_ERROR"
    assert stored["last_run_error_count"] == 4




def test_resume_text_alone_supplies_skills_summary_and_portfolio_for_matching_and_draft():
    profile = {
        "full_name": "MR FERISI",
        "email": "mr343ai@gmail.com",
        "resume_text": """# MR FERISI
## PROFESSIONAL SUMMARY
Creative digital professional with practical project-based experience in website development and branding.
## TECHNICAL SKILLS
- Web Development: HTML, CSS, JavaScript.
- Frontend: React and JSX.
- Backend: Python and FastAPI (project-based).
- Graphic Design: Logos, banners, posters and branding.
## SELECTED DIGITAL PROJECTS
MO SaaS: https://mo-tec.github.io/SaaS/
MOOG Digital: https://moog-digital.blogspot.com/
""",
    }
    job = {
        "title": "React Web Developer",
        "company": "Example Studio",
        "description": "Build web applications using JavaScript, React, HTML and CSS.",
        "tags": ["frontend", "web development"],
    }

    assert jobs._profile_ready(profile) is True
    assert jobs._match_score(job, profile) == 100
    draft = jobs._build_application_draft(job, profile)
    assert draft is not None
    assert "practical project-based experience in website development and branding" in draft["cover_letter"]
    assert "React" in draft["cover_letter"]
    assert "https://mo-tec.github.io/SaaS/" in draft["cover_letter"]


def test_resume_text_is_used_when_refreshing_waiting_draft():
    db = make_db()
    task = Task(
        user_id=23,
        title="Application prep: React Web Developer",
        description="Company: Example Studio\\nRole: React Web Developer\\nJob URL: https://jobs.example.test/role",
        status="WAITING_FOR_PROFILE",
        priority="NORMAL",
        agent="jobs",
        source="autopilot",
        result=json.dumps({
            "workflow": "JOB_APPLICATION",
            "status": "WAITING_FOR_PROFILE",
            "job": {
                "title": "React Web Developer",
                "company": "Example Studio",
                "url": "https://jobs.example.test/role",
                "description": "React, JavaScript and CSS.",
                "location": "Worldwide",
                "tags": ["frontend"],
            },
            "application_draft": None,
            "submission": {"status": "NOT_SUBMITTED"},
        }),
    )
    db.add(task)
    db.commit()
    profile = {
        "full_name": "MR FERISI",
        "email": "mr343ai@gmail.com",
        "resume_text": """## PROFESSIONAL SUMMARY
Project-based web development.
## TECHNICAL SKILLS
- Frontend: React, JavaScript, CSS.""",
    }

    assert jobs._refresh_waiting_application_drafts(db, 23, profile) == 1
    packet = json.loads(db.query(Task).one().result)
    assert packet["status"] == "READY_FOR_REVIEW"
    assert "Project-based web development" in packet["application_draft"]["cover_letter"]
    assert packet["match_score"] is not None

def test_import_job_application_profile_from_owner_cv_memory():
    db = make_db()
    cv = """# MR FERISI
Email: mr343ai@gmail.com
## PROFESSIONAL SUMMARY
Creative digital professional with project-based website development and branding experience.
## TECHNICAL SKILLS
- Web Development: HTML, CSS, JavaScript.
- Frontend: React and JSX.
- Backend: Python and FastAPI (project-based).
- Graphic Design: Logos, banners, posters and branding.
"""
    db.add(Memory(user_id=31, key="cv_resume", value=cv))
    db.commit()

    result = jobs.import_job_application_profile_from_memory(SimpleNamespace(id=31), db)
    profile = jobs._read_json_setting(db, 31, jobs.APPLICATION_PROFILE_KEY, {})

    assert result["status"] == "IMPORTED"
    assert result["profile_ready"] is True
    assert {"resume_text", "email", "full_name", "skills", "experience_summary"}.issubset(
        set(result["imported_fields"])
    )
    assert profile["full_name"] == "MR FERISI"
    assert profile["email"] == "mr343ai@gmail.com"
    assert any("react" in skill.casefold() for skill in profile["skills"])
    assert "project-based website development" in profile["experience_summary"]
    db.close()


def test_import_job_application_profile_never_reads_another_owner_memory():
    db = make_db()
    db.add(Memory(
        user_id=99,
        key="cv_resume",
        value="""# DIFFERENT OWNER
Email: other@example.com
## TECHNICAL SKILLS
- Python, accounting""",
    ))
    db.commit()

    result = jobs.import_job_application_profile_from_memory(SimpleNamespace(id=31), db)

    assert result["status"] == "NOT_FOUND"
    assert result["imported_fields"] == []
    assert db.query(Setting).filter_by(
        user_id=31,
        key=jobs.APPLICATION_PROFILE_KEY,
    ).count() == 0
    db.close()


def test_import_job_application_profile_does_not_overwrite_manual_fields_or_secrets():
    db = make_db()
    db.add(Setting(
        user_id=41,
        key=jobs.APPLICATION_PROFILE_KEY,
        value=json.dumps({
            "full_name": "MR FERISI",
            "email": "manual@example.com",
            "skills": ["Owner-entered skill"],
        }),
    ))
    db.add(Memory(
        user_id=41,
        key="cv_resume",
        value="""# OTHER NAME
Email: cv@example.com
## PROFESSIONAL SUMMARY
A saved CV summary.""",
    ))
    db.add(Memory(
        user_id=41,
        key="api_key",
        value="sk-do-not-import-this-value-12345678901234567890",
    ))
    db.commit()

    result = jobs.import_job_application_profile_from_memory(SimpleNamespace(id=41), db)
    profile = jobs._read_json_setting(db, 41, jobs.APPLICATION_PROFILE_KEY, {})

    assert result["status"] == "IMPORTED"
    assert profile["full_name"] == "MR FERISI"
    assert profile["email"] == "manual@example.com"
    assert profile["skills"] == ["Owner-entered skill"]
    assert profile["resume_text"].startswith("# OTHER NAME")
    assert "sk-do-not-import-this-value" not in str(profile)
    db.close()




def test_tanzania_job_eligibility_requires_explicit_country_access():
    assert jobs._tanzania_job_eligibility({
        "location": "Dar es Salaam, Tanzania",
    })[0] == "ELIGIBLE"
    assert jobs._tanzania_job_eligibility({
        "location": "Worldwide",
    })[0] == "ELIGIBLE"
    assert jobs._tanzania_job_eligibility({
        "location": "Remote",
        "description": "This role is open to applicants worldwide.",
    })[0] == "ELIGIBLE"
    assert jobs._tanzania_job_eligibility({
        "location": "Remote",
        "description": "Applicants must be based in the United States.",
    })[0] == "NOT_ELIGIBLE"
    assert jobs._tanzania_job_eligibility({
        "location": "Remote",
        "description": "US citizens only.",
    })[0] == "NOT_ELIGIBLE"
    assert jobs._tanzania_job_eligibility({
        "location": "Remote",
        "description": "A remote position with no country information.",
    })[0] == "UNVERIFIED"


def test_job_autopilot_only_creates_tasks_for_tanzania_eligible_listings(monkeypatch):
    db = make_db()
    rows = [
        {
            **sample_result("graphic designer")["results"][0],
            "id": "worldwide-role",
            "title": "Worldwide Graphic Designer",
            "location": "Worldwide",
            "url": "https://jobs.example.test/worldwide",
        },
        {
            **sample_result("graphic designer")["results"][0],
            "id": "us-only-role",
            "title": "US-only Graphic Designer",
            "location": "Remote",
            "description": "Applicants must be based in the United States.",
            "url": "https://jobs.example.test/us-only",
        },
        {
            **sample_result("graphic designer")["results"][0],
            "id": "unknown-role",
            "title": "Remote Graphic Designer",
            "location": "Remote",
            "description": "Create graphics for a distributed team.",
            "url": "https://jobs.example.test/unknown-country",
        },
    ]

    async def fake_research(query, limit=25):
        return {
            "status": "COMPLETED",
            "query": query,
            "count": len(rows),
            "results": [dict(row) for row in rows],
            "sources": ["Remotive"],
            "source_warnings": [],
        }

    monkeypatch.setattr(jobs, "research_public_jobs", fake_research)
    result = asyncio.run(jobs.run_job_autopilot_for_user(db, 52, force=True))
    tasks = db.query(Task).filter(Task.user_id == 52, Task.source == "autopilot").all()

    assert result["candidate_count"] == 3
    assert result["eligible_candidate_count"] == 1
    assert result["excluded_location"] == 1
    assert result["unverified_location"] == 1
    assert result["new_jobs"] == 1
    assert len(tasks) == 1
    assert "worldwide" in tasks[0].description.casefold()
    db.close()


def test_profile_refresh_never_prepares_application_for_us_only_remote_job():
    db = make_db()
    job = {
        "title": "Remote Customer Support Specialist",
        "company": "Example US Employer",
        "url": "https://jobs.example.test/us-support",
        "location": "Remote",
        "description": "Applicants must be located in the United States.",
        "tags": ["customer support"],
    }
    task = Task(
        user_id=62,
        title="Application prep: Remote Customer Support Specialist",
        description="Company: Example US Employer",
        status="WAITING_FOR_PROFILE",
        priority="NORMAL",
        agent="jobs",
        source="autopilot",
        result=json.dumps({
            "workflow": "JOB_APPLICATION",
            "status": "WAITING_FOR_PROFILE",
            "job": job,
            "application_draft": None,
            "submission": {"status": "NOT_SUBMITTED"},
        }),
    )
    db.add(task)
    db.flush()
    db.add(TaskStep(task_id=task.id, position=2, title="Prepare application", state="pending"))
    db.commit()

    profile = {
        "full_name": "MR FERISI",
        "email": "mr343ai@gmail.com",
        "skills": ["customer support", "communication"],
        "experience_summary": "Customer support and digital services.",
    }
    refreshed = jobs._refresh_waiting_application_drafts(db, 62, profile)
    db.commit()
    db.refresh(task)
    packet = json.loads(task.result)

    assert refreshed == 0
    assert task.status == "NOT_ELIGIBLE"
    assert packet["application_draft"] is None
    assert packet["location_eligibility"] == "NOT_ELIGIBLE"
    assert packet["submission"]["status"] == "NOT_SUBMITTED"
    db.close()


def test_profile_refresh_keeps_generic_remote_job_waiting_for_eligibility():
    db = make_db()
    task = Task(
        user_id=63,
        title="Application prep: Remote Designer",
        description="Company: Example Studio",
        status="WAITING_FOR_PROFILE",
        priority="NORMAL",
        agent="jobs",
        source="autopilot",
        result=json.dumps({
            "workflow": "JOB_APPLICATION",
            "status": "WAITING_FOR_PROFILE",
            "job": {
                "title": "Remote Designer",
                "company": "Example Studio",
                "url": "https://jobs.example.test/remote-designer",
                "location": "Remote",
                "description": "Design assets for a distributed team.",
                "tags": ["graphic design"],
            },
            "application_draft": None,
            "submission": {"status": "NOT_SUBMITTED"},
        }),
    )
    db.add(task)
    db.flush()
    db.add(TaskStep(task_id=task.id, position=2, title="Prepare application", state="pending"))
    db.commit()

    profile = {
        "full_name": "MR FERISI",
        "email": "mr343ai@gmail.com",
        "skills": ["graphic design"],
        "experience_summary": "Practical graphic design work.",
    }
    refreshed = jobs._refresh_waiting_application_drafts(db, 63, profile)
    db.commit()
    db.refresh(task)
    packet = json.loads(task.result)

    assert refreshed == 0
    assert task.status == "WAITING_FOR_ELIGIBILITY"
    assert packet["application_draft"] is None
    assert packet["location_eligibility"] == "UNVERIFIED"
    db.close()



def test_old_pending_tasks_are_location_classified_before_cv_is_ready():
    db = make_db()
    jobs_to_add = [
        {
            "title": "US-only Support Role",
            "company": "US Employer",
            "url": "https://jobs.example.test/us-only-pending",
            "location": "Remote",
            "description": "Applicants must be based in the United States.",
        },
        {
            "title": "Worldwide Graphic Designer",
            "company": "Global Employer",
            "url": "https://jobs.example.test/worldwide-pending",
            "location": "Worldwide",
            "description": "Graphic design for a distributed team.",
        },
        {
            "title": "Remote Designer",
            "company": "Unclear Employer",
            "url": "https://jobs.example.test/unclear-pending",
            "location": "Remote",
            "description": "Graphic design for a distributed team.",
        },
    ]
    tasks = []
    for index, job in enumerate(jobs_to_add, start=1):
        task = Task(
            user_id=64,
            title=f"Application prep: {job['title']}",
            description=f"Company: {job['company']}",
            status="WAITING_FOR_PROFILE",
            priority="NORMAL",
            agent="jobs",
            source="autopilot",
            result=json.dumps({
                "workflow": "JOB_APPLICATION",
                "status": "WAITING_FOR_PROFILE",
                "job": job,
                "application_draft": None,
                "submission": {"status": "NOT_SUBMITTED"},
            }),
        )
        db.add(task)
        db.flush()
        db.add(TaskStep(task_id=task.id, position=2, title="Prepare application", state="pending"))
        tasks.append(task)
    db.commit()

    refreshed = jobs._refresh_waiting_application_drafts(db, 64, {})
    db.commit()
    for task in tasks:
        db.refresh(task)
    packets = [json.loads(task.result) for task in tasks]

    assert refreshed == 0
    assert tasks[0].status == "NOT_ELIGIBLE"
    assert packets[0]["application_draft"] is None
    assert tasks[1].status == "WAITING_FOR_PROFILE"
    assert packets[1]["location_eligibility"] == "ELIGIBLE"
    assert tasks[2].status == "WAITING_FOR_ELIGIBILITY"
    assert packets[2]["location_eligibility"] == "UNVERIFIED"
    db.close()
