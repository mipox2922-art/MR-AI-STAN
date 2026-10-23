import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ApprovalRequest, Task, TaskStep
from app.orchestration.executor import execute_mission
from app.orchestration.planner import select_agents
from app.routers.agents import claim_browser_command, report_browser_command_result


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=True, autocommit=False)()


def valid_page_result():
    return {
        "action": "GET_PAGE_DATA",
        "verified": True,
        "targetHost": "127.0.0.1",
        "targetUrl": "http://127.0.0.1:4173/",
        "targetTitle": "MR AI Browser Fixture",
        "page": {
            "title": "MR AI Browser Fixture",
            "url": "http://127.0.0.1:4173/",
            "text": "fixture ready\nBrowser Hands end-to-end marker",
        },
    }


def test_read_page_mission_is_routed_to_browser_and_durably_queued():
    db = make_db()
    user = SimpleNamespace(id=901)

    assert select_agents("soma ukurasa") == ["browser"]
    result = asyncio.run(execute_mission("soma ukurasa", user, db))

    mission = db.query(Task).filter_by(user_id=user.id, agent="orchestrator").one()
    command = db.query(Task).filter_by(user_id=user.id, agent="browser", source="browser_hands").one()

    assert result["status"] == "WAITING_FOR_HAND"
    assert mission.status == "WAITING_FOR_HAND"
    assert command.status == "QUEUED"
    assert command.approved_by == user.id
    descriptor = json.loads(command.description)
    assert descriptor["mission_id"] == mission.id
    assert descriptor["step_position"] == 1
    assert descriptor["request_id"] == f"browser-task-{command.id}"
    assert descriptor["action"] == "GET_PAGE_DATA"
    assert db.query(ApprovalRequest).count() == 0
    db.close()


def test_extension_claim_result_verifies_and_persists_the_parent_mission():
    db = make_db()
    user = SimpleNamespace(id=902)
    asyncio.run(execute_mission("soma ukurasa", user, db))
    mission = db.query(Task).filter_by(user_id=user.id, agent="orchestrator").one()
    browser_task = db.query(Task).filter_by(user_id=user.id, agent="browser", source="browser_hands").one()

    claimed = claim_browser_command(current_user=user, db=db)
    command = claimed["command"]
    assert claimed["status"] == "RUNNING"
    assert command["task_id"] == browser_task.id
    assert command["request_id"] == f"browser-task-{browser_task.id}"
    assert len(command["claim_token"]) >= 32
    db.refresh(browser_task)
    assert browser_task.status == "RUNNING"

    payload = {
        "request_id": command["request_id"],
        "claim_token": command["claim_token"],
        "result": valid_page_result(),
    }
    returned = report_browser_command_result(
        browser_task.id, payload, current_user=user, db=db
    )

    db.refresh(mission)
    db.refresh(browser_task)
    step = db.query(TaskStep).filter_by(task_id=mission.id, position=1).one()
    saved = json.loads(browser_task.result)
    parent_packet = json.loads(mission.result)

    assert returned["status"] == "COMPLETED"
    assert returned["verified"] is True
    assert browser_task.status == "COMPLETED"
    assert mission.status == "COMPLETED"
    assert mission.progress == 100
    assert step.state == "verified"
    assert step.verified_at is not None
    assert saved["request_id"] == command["request_id"]
    assert saved["verified"] is True
    assert saved["result"]["page"]["text"].startswith("fixture ready")
    assert parent_packet["verified_steps"] == 1
    assert parent_packet["steps"][0]["status"] == "COMPLETED"
    assert parent_packet["steps"][0]["command_task_id"] == browser_task.id

    duplicate = report_browser_command_result(
        browser_task.id, payload, current_user=user, db=db
    )
    assert duplicate["status"] == "ALREADY_RECORDED"
    assert db.query(TaskStep).filter_by(task_id=mission.id).count() == 1
    db.close()


def test_extension_result_requires_owner_scope_request_id_and_claim_token():
    db = make_db()
    user = SimpleNamespace(id=903)
    other_user = SimpleNamespace(id=904)
    asyncio.run(execute_mission("soma ukurasa", user, db))
    browser_task = db.query(Task).filter_by(user_id=user.id, agent="browser", source="browser_hands").one()
    command = claim_browser_command(current_user=user, db=db)["command"]
    payload = {
        "request_id": command["request_id"],
        "claim_token": "forged-token",
        "result": valid_page_result(),
    }

    with pytest.raises(HTTPException) as invalid_claim:
        report_browser_command_result(browser_task.id, payload, current_user=user, db=db)
    assert invalid_claim.value.status_code == 409

    with pytest.raises(HTTPException) as other_owner:
        report_browser_command_result(
            browser_task.id,
            {**payload, "claim_token": command["claim_token"]},
            current_user=other_user,
            db=db,
        )
    assert other_owner.value.status_code == 404

    db.refresh(browser_task)
    assert browser_task.status == "RUNNING"
    db.close()


def test_browser_allowlist_failure_is_persisted_as_blocked_not_completed():
    db = make_db()
    user = SimpleNamespace(id=905)
    asyncio.run(execute_mission("soma ukurasa", user, db))
    mission = db.query(Task).filter_by(user_id=user.id, agent="orchestrator").one()
    browser_task = db.query(Task).filter_by(user_id=user.id, agent="browser", source="browser_hands").one()
    command = claim_browser_command(current_user=user, db=db)["command"]

    result = report_browser_command_result(
        browser_task.id,
        {
            "request_id": command["request_id"],
            "claim_token": command["claim_token"],
            "error": "BLOCKED_BY_ALLOWLIST: domain not approved",
        },
        current_user=user,
        db=db,
    )
    db.refresh(browser_task)
    db.refresh(mission)
    assert result["status"] == "BLOCKED"
    assert browser_task.status == "BLOCKED"
    assert mission.status == "BLOCKED"
    assert mission.progress == 0
    assert "allowlist" in (mission.error or "").lower()
    db.close()


def test_unverified_navigation_response_does_not_mark_a_mission_completed():
    db = make_db()
    user = SimpleNamespace(id=906)
    result = asyncio.run(execute_mission("fungua https://example.com", user, db))
    assert result["status"] in {"WAITING_FOR_HAND", "WAITING_APPROVAL"}
    # Navigation is an externally visible action and stays blocked unless the
    # request is explicitly dispatched and a resulting page state is verified.
    if result["status"] == "WAITING_FOR_HAND":
        mission = db.query(Task).filter_by(user_id=user.id, agent="orchestrator").one()
        browser_task = db.query(Task).filter_by(user_id=user.id, agent="browser", source="browser_hands").one()
        command = claim_browser_command(current_user=user, db=db)["command"]
        returned = report_browser_command_result(
            browser_task.id,
            {
                "request_id": command["request_id"],
                "claim_token": command["claim_token"],
                "result": {
                    "action": "NAVIGATE",
                    "verified": False,
                    "dispatched": True,
                    "targetHost": "127.0.0.1",
                    "targetUrl": "http://127.0.0.1:4173/",
                    "targetTitle": "Fixture",
                    "target": "https://example.com/",
                },
            },
            current_user=user,
            db=db,
        )
        db.refresh(mission)
        assert returned["status"] == "WAITING_FOR_VERIFICATION"
        assert mission.status == "WAITING_FOR_VERIFICATION"
        assert mission.progress == 0
        assert mission.status != "COMPLETED"
    db.close()


def test_resuming_a_waiting_mission_does_not_enqueue_a_duplicate_browser_action():
    db = make_db()
    user = SimpleNamespace(id=907)

    first = asyncio.run(execute_mission("soma ukurasa", user, db))
    mission = db.query(Task).filter_by(user_id=user.id, agent="orchestrator").one()
    original = db.query(Task).filter_by(
        user_id=user.id, agent="browser", source="browser_hands"
    ).one()

    resumed = asyncio.run(execute_mission("soma ukurasa", user, db, mission=mission))

    commands = db.query(Task).filter_by(
        user_id=user.id,
        agent="browser",
        source="browser_hands",
        requested_by=f"mission:{mission.id}",
    ).all()
    assert first["status"] == "WAITING_FOR_HAND"
    assert resumed["status"] == "WAITING_FOR_HAND"
    assert len(commands) == 1
    assert commands[0].id == original.id
    assert commands[0].status == "QUEUED"
    db.close()
