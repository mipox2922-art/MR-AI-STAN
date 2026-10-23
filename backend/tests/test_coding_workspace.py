import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Task
from app.orchestration.executor import execute_mission
from app.orchestration.planner import select_agents

from app.config import settings
from app.connectors.coding_workspace import (
    CodingWorkspaceError,
    _validate_configuration,
    coding_workspace_status,
    validate_workspace_path,
)


def test_coding_workspace_is_truthfully_not_connected_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "coding_github_token", "")
    monkeypatch.setattr(settings, "coding_github_repository", "")
    status = coding_workspace_status()
    assert status["status"] == "NOT_CONNECTED"
    assert status["configured"] is False
    assert status["operations"] == []
    assert "token" not in status
    with pytest.raises(CodingWorkspaceError) as error:
        _validate_configuration()
    assert error.value.status_code == 503


def test_coding_workspace_accepts_only_expected_source_roots():
    assert validate_workspace_path("backend/app/main.py") == "backend/app/main.py"
    assert validate_workspace_path("web/src/App.jsx") == "web/src/App.jsx"
    assert validate_workspace_path("extension/background.js") == "extension/background.js"
    assert validate_workspace_path(".github/workflows/ci.yml") == ".github/workflows/ci.yml"


@pytest.mark.parametrize("path", [
    "/backend/app/main.py",
    "backend/../.env",
    "backend/app/../../web/src/App.jsx",
    "web/.env.local",
    "backend/private.pem",
    "backend/store.sqlite",
    "README.md",
    "web//src/App.jsx",
    "web/./src/App.jsx",
])
def test_coding_workspace_rejects_traversal_secrets_and_unapproved_roots(path):
    with pytest.raises(CodingWorkspaceError) as error:
        validate_workspace_path(path)
    assert error.value.status_code == 400


def test_coding_workspace_refuses_production_branch(monkeypatch):
    monkeypatch.setattr(settings, "coding_github_token", "test-token-not-used-for-network")
    monkeypatch.setattr(settings, "coding_github_repository", "owner/repo")
    monkeypatch.setattr(settings, "coding_github_base_branch", "main")
    monkeypatch.setattr(settings, "coding_github_work_branch", "main")
    status = coding_workspace_status()
    assert status["configured"] is False
    with pytest.raises(CodingWorkspaceError) as error:
        _validate_configuration()
    assert error.value.status_code == 503


def test_coding_workspace_uses_isolated_configured_branch(monkeypatch):
    monkeypatch.setattr(settings, "coding_github_token", "test-token-not-used-for-network")
    monkeypatch.setattr(settings, "coding_github_repository", "owner/repo")
    monkeypatch.setattr(settings, "coding_github_base_branch", "main")
    monkeypatch.setattr(settings, "coding_github_work_branch", "mr-ai/coding-agent-work")
    status = coding_workspace_status()
    assert status["status"] == "CONFIGURED"
    assert status["configured"] is True
    assert status["work_branch"] == "mr-ai/coding-agent-work"
    assert "test-token-not-used-for-network" not in repr(status)


def _test_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=True, autocommit=False)()


def test_read_only_repository_review_routes_to_coding_agent():
    assert select_agents("chambua repo ya MR-AI-STAN kwa makosa") == ["coding"]
    assert select_agents("inspect repository source code") == ["coding"]


def test_coding_mission_reports_not_connected_without_fake_execution(monkeypatch):
    monkeypatch.setattr(settings, "coding_github_token", "")
    monkeypatch.setattr(settings, "coding_github_repository", "")
    db = _test_db()
    user = SimpleNamespace(id=908)

    result = asyncio.run(execute_mission("chambua repo ya MR-AI-STAN kwa makosa", user, db))

    mission = db.query(Task).filter_by(user_id=user.id, agent="orchestrator").one()
    packet = result["steps"][0]
    assert result["status"] == "WAITING_FOR_HAND"
    assert packet["agent"] == "coding"
    assert packet["tool"] == "coding_workspace"
    assert packet["status"] == "NOT_CONNECTED"
    assert packet["verified"] is False
    assert "CODING_GITHUB_TOKEN" in packet["evidence"]["message"]
    assert mission.status == "WAITING_FOR_HAND"
    assert mission.progress == 0
    db.close()


def test_coding_mutation_mission_requires_owner_approval(monkeypatch):
    monkeypatch.setattr(settings, "coding_github_token", "")
    monkeypatch.setattr(settings, "coding_github_repository", "")
    db = _test_db()
    user = SimpleNamespace(id=909)

    result = asyncio.run(execute_mission("rekebisha bug kwenye backend repository", user, db))

    assert result["status"] == "WAITING_APPROVAL"
    assert result["mission"]["status"] == "WAITING_APPROVAL"
    assert db.query(Task).filter_by(user_id=user.id, agent="orchestrator").count() == 1
    assert db.query(Task).filter_by(user_id=user.id, agent="coding").count() == 0
    db.close()
