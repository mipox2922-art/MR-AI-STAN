import asyncio
import json
import time

import pytest

from app.config import settings
from app.connectors import coding_agent
from app.connectors.coding_agent import (
    _apply_exact_edits,
    _candidate_paths,
    _free_provider_name,
    _sign_plan,
    apply_coding_plan,
    plan_coding_task,
    verify_coding_plan,
)
from app.connectors.coding_workspace import CodingWorkspaceError


def set_workspace(monkeypatch):
    monkeypatch.setattr(settings, "coding_github_token", "test-token-that-is-never-used-for-network")
    monkeypatch.setattr(settings, "coding_github_repository", "owner/repo")
    monkeypatch.setattr(settings, "coding_github_base_branch", "main")
    monkeypatch.setattr(settings, "coding_github_work_branch", "mr-ai/coding-agent-work")
    monkeypatch.setattr(settings, "secret_key", "test-coding-agent-secret-key-that-is-over-32-characters")


def test_coding_agent_only_selects_explicitly_free_providers(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "openrouter_model", "provider/paid-model")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "gemini_tier", "FREE")
    monkeypatch.setattr(settings, "mistral_api_key", "configured-but-not-used")
    monkeypatch.setattr(settings, "xai_api_key", "configured-but-not-used")
    monkeypatch.setattr(settings, "kimi_api_key", "configured-but-not-used")
    assert _free_provider_name() is None

    monkeypatch.setattr(settings, "gemini_api_key", "configured-gemini-key")
    assert _free_provider_name() == "gemini"

    monkeypatch.setattr(settings, "openrouter_api_key", "configured-openrouter-key")
    monkeypatch.setattr(settings, "openrouter_model", "meta-llama/llama-3:free")
    assert _free_provider_name() == "openrouter"


def test_exact_patch_edits_are_applied_only_when_target_is_unique():
    original = "def add(a, b):\n    return a - b\n"
    updated = _apply_exact_edits(
        "backend/app/math_utils.py",
        original,
        [{"old": "def add(a, b):\n    return a - b", "new": "def add(a, b):\n    return a + b"}],
    )
    assert updated == "def add(a, b):\n    return a + b\n"

    with pytest.raises(CodingWorkspaceError) as error:
        _apply_exact_edits("backend/app/math_utils.py", "x = 1\nx = 1\n", [{"old": "x = 1", "new": "x = 2"}])
    assert error.value.status_code == 409


def test_file_inventory_ranking_excludes_generated_and_secret_files():
    ranked = _candidate_paths(
        "fix browser chat and add regression test",
        [
            {"path": "web/src/components/Chat.jsx", "size": 500},
            {"path": "web/node_modules/pkg/index.js", "size": 300},
            {"path": "backend/.env.local", "size": 60},
            {"path": "backend/tests/test_chat.py", "size": 900},
            {"path": "web/dist/app.min.js", "size": 1200},
        ],
    )
    paths = [row["path"] for row in ranked]
    assert "web/src/components/Chat.jsx" in paths
    assert "backend/tests/test_chat.py" in paths
    assert all("node_modules" not in path and ".env" not in path and "/dist/" not in path for path in paths)


def _signed_plan():
    return {
        "plan_id": "c" * 32,
        "request": "Fix a demonstrated arithmetic bug and add a test",
        "summary": "Fix addition",
        "risk": "LOW",
        "repository": "owner/repo",
        "base_branch": "main",
        "base_sha": "a" * 40,
        "provider": "gemini",
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + 1200,
        "files_reviewed": [{"path": "backend/app/math_utils.py", "sha": "blob-sha", "size": 32}],
        "changes": [{
            "path": "backend/app/math_utils.py",
            "action": "update",
            "original_sha": "blob-sha",
            "content": "def add(a, b):\n    return a + b\n",
            "diff": "--- a/backend/app/math_utils.py\n+++ b/backend/app/math_utils.py\n",
        }],
        "tests_to_run": ["pytest -q backend/tests"],
        "manual_checks": [],
        "execution_boundary": "Preview only",
    }


def test_signed_coding_proposal_rejects_tampering_and_expiry(monkeypatch):
    set_workspace(monkeypatch)
    plan = _signed_plan()
    signature = _sign_plan(plan)
    verified = verify_coding_plan(plan, signature)
    assert verified["plan_id"] == plan["plan_id"]

    tampered = dict(plan)
    tampered["changes"] = [dict(plan["changes"][0], content="malicious changed content")]
    with pytest.raises(CodingWorkspaceError) as error:
        verify_coding_plan(tampered, signature)
    assert error.value.status_code == 403

    expired = dict(plan, expires_at=int(time.time()) - 10)
    expired_signature = _sign_plan(expired)
    with pytest.raises(CodingWorkspaceError) as error:
        verify_coding_plan(expired, expired_signature)
    assert error.value.status_code == 409


def test_plan_generation_reads_sources_and_returns_preview_without_writing(monkeypatch):
    set_workspace(monkeypatch)
    monkeypatch.setattr(coding_agent, "coding_agent_status", lambda: {"configured": True})
    monkeypatch.setattr(coding_agent, "_free_provider_name", lambda: "gemini")
    monkeypatch.setattr(coding_agent, "_validate_configuration", lambda: (
        "fake-token", "owner/repo", "main", "mr-ai/coding-agent-work"
    ))

    async def fake_inventory(branch=None):
        return {
            "status": "COMPLETED",
            "repository": "owner/repo",
            "branch": "main",
            "commit_sha": "a" * 40,
            "files": [{"path": "backend/app/math_utils.py", "size": 34, "sha": "blob-sha"}],
        }

    original = "def add(a, b):\n    return a - b\n"

    async def fake_inspect(paths, branch=None):
        assert paths == ["backend/app/math_utils.py"]
        return {"status": "COMPLETED", "files": [{
            "path": "backend/app/math_utils.py", "sha": "blob-sha",
            "size": len(original), "content": original, "truncated": False, "status": "COMPLETED",
        }]}

    generated = [
        json.dumps({"files": ["backend/app/math_utils.py"], "reason": "Request names arithmetic behavior"}),
        json.dumps({
            "summary": "Fix addition implementation",
            "risk": "LOW",
            "changes": [{
                "path": "backend/app/math_utils.py",
                "action": "update",
                "edits": [{
                    "old": "def add(a, b):\n    return a - b",
                    "new": "def add(a, b):\n    return a + b",
                }],
            }],
            "tests_to_run": ["pytest -q backend/tests"],
            "manual_checks": [],
        }),
    ]

    async def fake_generate(provider_name, prompt, stage):
        assert provider_name == "gemini"
        return generated.pop(0)

    monkeypatch.setattr(coding_agent, "list_source_files", fake_inventory)
    monkeypatch.setattr(coding_agent, "inspect_files", fake_inspect)
    monkeypatch.setattr(coding_agent, "_generate", fake_generate)

    result = asyncio.run(plan_coding_task("Fix the broken add operation and propose a regression test."))

    assert result["status"] == "PLAN_READY"
    assert result["plan"]["changes"][0]["content"] == "def add(a, b):\n    return a + b\n"
    assert result["plan"]["base_sha"] == "a" * 40
    assert result["proposal_signature"] == _sign_plan(result["plan"])
    assert len(generated) == 0


def test_apply_coding_plan_commits_isolated_branch_and_opens_pr(monkeypatch):
    set_workspace(monkeypatch)
    plan = _signed_plan()
    signature = _sign_plan(plan)
    committed_calls = []
    pr_calls = []

    async def fake_commit(files, **kwargs):
        committed_calls.append((files, kwargs))
        return {
            "status": "COMMITTED",
            "repository": "owner/repo",
            "branch": kwargs["branch"],
            "base_branch": "main",
            "base_sha": plan["base_sha"],
            "commit_sha": "b" * 40,
            "commit_url": "https://github.com/owner/repo/commit/" + "b" * 40,
            "changed_files": ["backend/app/math_utils.py"],
            "ci": "PENDING",
        }

    async def fake_pr(branch, *, title, body):
        pr_calls.append((branch, title, body))
        return {"status": "OPENED", "number": 12, "url": "https://github.com/owner/repo/pull/12"}

    monkeypatch.setattr(coding_agent, "commit_files_atomically", fake_commit)
    monkeypatch.setattr(coding_agent, "create_pull_request", fake_pr)

    result = asyncio.run(apply_coding_plan(plan, signature))

    assert result["status"] == "PR_OPENED"
    assert result["commit_sha"] == "b" * 40
    assert result["pull_request"]["number"] == 12
    assert committed_calls[0][1]["expected_base_sha"] == plan["base_sha"]
    assert committed_calls[0][1]["branch"].startswith("mr-ai/coding-agent/")
    assert len(pr_calls) == 1
    assert result["ci"] == "PENDING"


def test_apply_coding_plan_never_calls_a_provider_during_apply(monkeypatch):
    set_workspace(monkeypatch)
    plan = _signed_plan()
    signature = _sign_plan(plan)
    monkeypatch.setattr(coding_agent, "_free_provider_name", lambda: None)

    async def fake_commit(files, **kwargs):
        return {"status": "COMMITTED", "repository": "owner/repo", "branch": kwargs["branch"],
                "base_branch": "main", "base_sha": plan["base_sha"], "commit_sha": "b" * 40,
                "commit_url": "https://github.com/owner/repo/commit/" + "b" * 40,
                "changed_files": ["backend/app/math_utils.py"], "ci": "PENDING"}

    async def fake_pr(branch, *, title, body):
        return {"status": "OPENED", "number": 12, "url": "https://github.com/owner/repo/pull/12"}

    monkeypatch.setattr(coding_agent, "commit_files_atomically", fake_commit)
    monkeypatch.setattr(coding_agent, "create_pull_request", fake_pr)
    result = asyncio.run(apply_coding_plan(plan, signature))
    assert result["status"] == "PR_OPENED"
