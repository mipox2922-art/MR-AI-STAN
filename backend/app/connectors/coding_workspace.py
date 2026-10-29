from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import quote

import httpx

from ..config import settings


_GITHUB_API = "https://api.github.com"
_ALLOWED_PREFIXES = ("backend/", "web/", "extension/", "device-bridge/", ".github/workflows/")
_FORBIDDEN_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,180}$")
_MAX_FILE_BYTES = 250_000


class CodingWorkspaceError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _configuration() -> tuple[str, str, str, str]:
    token = str(settings.coding_github_token or "").strip()
    repository = str(settings.coding_github_repository or "").strip()
    base_branch = str(settings.coding_github_base_branch or "main").strip()
    work_branch = str(settings.coding_github_work_branch or "mr-ai/coding-agent-work").strip()
    return token, repository, base_branch, work_branch


def _validate_configuration() -> tuple[str, str, str, str]:
    token, repository, base_branch, work_branch = _configuration()
    if not token or not repository:
        raise CodingWorkspaceError(
            "Coding Agent is not connected. Configure CODING_GITHUB_TOKEN and CODING_GITHUB_REPOSITORY in the backend environment.",
            503,
        )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise CodingWorkspaceError("CODING_GITHUB_REPOSITORY must be an owner/repository slug.", 503)
    if not base_branch or not _BRANCH_RE.fullmatch(base_branch):
        raise CodingWorkspaceError("CODING_GITHUB_BASE_BRANCH is invalid.", 503)
    if (
        not _BRANCH_RE.fullmatch(work_branch)
        or work_branch == base_branch
        or work_branch.casefold() in {"main", "master", "production", "prod"}
    ):
        raise CodingWorkspaceError(
            "Coding Agent work branch must be a separate, non-production branch.",
            503,
        )
    return token, repository, base_branch, work_branch


def validate_work_branch(raw_branch: str) -> str:
    """Allow the configured work branch or an isolated per-task Coding Agent branch."""
    _, _, base_branch, configured_branch = _validate_configuration()
    branch = str(raw_branch or "").strip()
    parts = branch.split("/")
    valid_shape = (
        bool(_BRANCH_RE.fullmatch(branch))
        and all(part not in {"", ".", ".."} for part in parts)
        and branch != base_branch
        and branch.casefold() not in {"main", "master", "production", "prod"}
    )
    is_agent_branch = branch.startswith("mr-ai/coding-agent/") and len(parts) >= 3
    if not valid_shape or (branch != configured_branch and not is_agent_branch):
        raise CodingWorkspaceError(
            "Coding Agent may write only to its configured work branch or an isolated mr-ai/coding-agent/* branch.",
            400,
        )
    return branch


def validate_workspace_path(raw_path: str) -> str:
    path = str(raw_path or "").strip().replace("\\", "/")
    if (
        not path
        or path.startswith("/")
        or "\x00" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or path.split("/")[-1].casefold() in _FORBIDDEN_NAMES
        or path.lower().endswith((".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"))
        or not any(path.startswith(prefix) for prefix in _ALLOWED_PREFIXES)
    ):
        raise CodingWorkspaceError(
            "Path is outside the Coding Agent workspace allowlist or names a protected secret/data file.",
            400,
        )
    return path


def coding_workspace_status() -> dict[str, Any]:
    token, repository, base_branch, work_branch = _configuration()
    configured = bool(token and repository)
    branch_safe = bool(
        _BRANCH_RE.fullmatch(work_branch)
        and work_branch != base_branch
        and work_branch.casefold() not in {"main", "master", "production", "prod"}
    )
    return {
        "status": "CONFIGURED" if configured and branch_safe else "NOT_CONNECTED",
        "configured": configured and branch_safe,
        "repository": repository or None,
        "base_branch": base_branch or "main",
        "work_branch": work_branch if branch_safe else None,
        "provider": "GitHub REST API",
        "operations": ["inspect_files", "generate_patch", "commit_isolated_branch", "open_pull_request", "read_ci_checks"] if configured and branch_safe else [],
        "local_shell": "NOT_CONNECTED",
        "execution_mode": "GITHUB_BRANCH_AND_ACTIONS",
        "message": (
            "Coding Agent uses a free configured AI provider to propose a patch, commits only to isolated mr-ai/coding-agent/* branches, opens a pull request, and verifies tests from GitHub Actions. No production branch is modified directly."
            if configured and branch_safe
            else "Configure CODING_GITHUB_TOKEN and CODING_GITHUB_REPOSITORY. No repository changes can be executed until credentials are available."
        ),
    }


async def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    token, repository, _, _ = _validate_configuration()
    url = _GITHUB_API + path
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "MR-AI-STAN-Coding-Agent",
    }
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.request(method, url, headers=headers, json=json_body)
    except httpx.HTTPError as exc:
        raise CodingWorkspaceError("GitHub workspace request failed: " + type(exc).__name__, 502) from exc

    if response.status_code == 404:
        raise CodingWorkspaceError("GitHub repository, branch or file was not found; verify repository access and branch configuration.", 404)
    if response.status_code in {401, 403}:
        raise CodingWorkspaceError("GitHub rejected the coding token or its repository permissions. Check token scope without sharing the token.", 503)
    if response.status_code == 409:
        raise CodingWorkspaceError("GitHub reported a reference/content conflict. Refresh the branch before retrying.", 409)
    if response.status_code == 422:
        raise CodingWorkspaceError("GitHub rejected the requested change. Check branch protection, file SHA, and commit message.", 422)
    if not response.is_success:
        raise CodingWorkspaceError("GitHub workspace returned HTTP " + str(response.status_code) + ".", 502)
    try:
        data = response.json()
    except ValueError as exc:
        raise CodingWorkspaceError("GitHub returned invalid JSON.", 502) from exc
    if not isinstance(data, (dict, list)):
        raise CodingWorkspaceError("GitHub returned an unexpected response shape.", 502)
    return data


def _repo_path(repository: str, suffix: str) -> str:
    return "/repos/" + repository + suffix


async def get_branch_head_sha(branch: str | None = None) -> str:
    _, repository, base_branch, configured_work_branch = _validate_configuration()
    chosen = branch or base_branch
    if chosen != base_branch and chosen != configured_work_branch:
        validate_work_branch(chosen)
    result = await _request("GET", _repo_path(repository, "/git/ref/heads/" + quote(chosen, safe="/")))
    sha = str((result.get("object") or {}).get("sha") or "")
    if not sha:
        raise CodingWorkspaceError("GitHub branch did not return a commit SHA.", 502)
    return sha


async def list_source_files(branch: str | None = None) -> dict[str, Any]:
    """Return a bounded path inventory from the configured GitHub repository."""
    _, repository, base_branch, configured_work_branch = _validate_configuration()
    chosen = branch or base_branch
    if chosen != base_branch and chosen != configured_work_branch:
        validate_work_branch(chosen)
    ref = await _request("GET", _repo_path(repository, "/git/ref/heads/" + quote(chosen, safe="/")))
    commit_sha = str((ref.get("object") or {}).get("sha") or "")
    if not commit_sha:
        raise CodingWorkspaceError("GitHub branch did not return a commit SHA.", 502)
    commit = await _request(
        "GET",
        _repo_path(repository, "/git/commits/" + quote(commit_sha, safe="")),
    )
    tree_sha = str((commit.get("tree") or {}).get("sha") or "") if isinstance(commit, dict) else ""
    if not tree_sha:
        raise CodingWorkspaceError("GitHub branch commit did not return its tree SHA.", 502)
    tree = await _request(
        "GET",
        _repo_path(repository, "/git/trees/" + quote(tree_sha, safe="") + "?recursive=1"),
    )
    entries = tree.get("tree") if isinstance(tree, dict) else None
    if not isinstance(entries, list):
        raise CodingWorkspaceError("GitHub did not return a repository file tree.", 502)
    paths = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        raw_path = str(entry.get("path") or "")
        if not raw_path.startswith(_ALLOWED_PREFIXES):
            continue
        try:
            path = validate_workspace_path(raw_path)
        except CodingWorkspaceError:
            continue
        paths.append({"path": path, "size": int(entry.get("size") or 0), "sha": entry.get("sha")})
    return {
        "status": "COMPLETED",
        "repository": repository,
        "branch": chosen,
        "commit_sha": commit_sha,
        "truncated": bool(tree.get("truncated", False)),
        "files": paths[:5000],
    }


async def _ensure_work_branch(branch_override: str | None = None) -> tuple[str, str]:
    token, repository, base_branch, configured_work_branch = _validate_configuration()
    work_branch = validate_work_branch(branch_override or configured_work_branch)
    base_ref = quote(base_branch, safe="/")
    work_ref = quote(work_branch, safe="/")
    base = await _request("GET", _repo_path(repository, "/git/ref/heads/" + base_ref))
    base_sha = str((base.get("object") or {}).get("sha") or "")
    if not base_sha:
        raise CodingWorkspaceError("GitHub base branch did not return a commit SHA.", 502)
    try:
        current = await _request("GET", _repo_path(repository, "/git/ref/heads/" + work_ref))
        current_sha = str((current.get("object") or {}).get("sha") or "")
        if current_sha:
            return work_branch, current_sha
    except CodingWorkspaceError as exc:
        if exc.status_code != 404:
            raise
    try:
        await _request("POST", _repo_path(repository, "/git/refs"), json_body={
            "ref": "refs/heads/" + work_branch,
            "sha": base_sha,
        })
    except CodingWorkspaceError as exc:
        if exc.status_code != 422:
            raise
    current = await _request("GET", _repo_path(repository, "/git/ref/heads/" + work_ref))
    current_sha = str((current.get("object") or {}).get("sha") or "")
    if not current_sha:
        raise CodingWorkspaceError("Could not initialize the isolated Coding Agent branch.", 502)
    return work_branch, current_sha


async def inspect_files(paths: list[str], *, branch: str | None = None) -> dict[str, Any]:
    _, repository, base_branch, work_branch = _validate_configuration()
    chosen_branch = branch or work_branch
    if chosen_branch not in {base_branch, work_branch}:
        validate_work_branch(chosen_branch)
    if not isinstance(paths, list) or not paths or len(paths) > 12:
        raise CodingWorkspaceError("Provide 1 to 12 workspace file paths.", 400)

    results: list[dict[str, Any]] = []
    for raw_path in paths:
        path = validate_workspace_path(raw_path)
        endpoint = _repo_path(repository, "/contents/" + quote(path, safe="/"))
        try:
            data = await _request("GET", endpoint + "?ref=" + quote(chosen_branch, safe="/"))
        except CodingWorkspaceError as exc:
            results.append({"path": path, "status": "NOT_FOUND" if exc.status_code == 404 else "FAILED", "error": str(exc)})
            continue
        if data.get("type") != "file":
            results.append({"path": path, "status": "NOT_A_FILE", "error": "Only individual files can be inspected."})
            continue
        try:
            decoded = base64.b64decode(str(data.get("content") or ""), validate=False).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            results.append({"path": path, "status": "UNREADABLE", "error": "File is not readable UTF-8 text."})
            continue
        results.append({
            "path": path,
            "status": "COMPLETED",
            "sha": data.get("sha"),
            "size": len(decoded.encode("utf-8")),
            "content": decoded[:150_000],
            "truncated": len(decoded) > 150_000,
        })
    return {
        "status": "COMPLETED" if results and all(item["status"] == "COMPLETED" for item in results) else "PARTIAL",
        "repository": repository,
        "branch": chosen_branch,
        "files": results,
    }


async def write_file(path: str, content: str, message: str, *, branch: str | None = None) -> dict[str, Any]:
    _, repository, _, configured_work_branch = _validate_configuration()
    work_branch = validate_work_branch(branch or configured_work_branch)
    normalized = validate_workspace_path(path)
    if not isinstance(content, str) or len(content.encode("utf-8")) > _MAX_FILE_BYTES:
        raise CodingWorkspaceError("File content exceeds the 250 KB limit.", 413)
    commit_message = str(message or "").strip()
    if not commit_message or len(commit_message) > 180 or "\n" in commit_message or "\r" in commit_message:
        raise CodingWorkspaceError("Commit message must be a single line of 1 to 180 characters.", 400)

    _, branch_sha = await _ensure_work_branch(work_branch)
    endpoint = _repo_path(repository, "/contents/" + quote(normalized, safe="/"))
    existing_sha = None
    try:
        existing = await _request("GET", endpoint + "?ref=" + quote(work_branch, safe="/"))
        if existing.get("type") != "file":
            raise CodingWorkspaceError("Target path is not an individual file.", 400)
        existing_sha = existing.get("sha")
    except CodingWorkspaceError as exc:
        if exc.status_code != 404:
            raise

    payload: dict[str, Any] = {
        "message": commit_message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": work_branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha
    result = await _request("PUT", endpoint, json_body=payload)
    commit = result.get("commit") or {}
    commit_sha = str(commit.get("sha") or "")
    if not commit_sha:
        raise CodingWorkspaceError("GitHub did not return the created commit SHA.", 502)
    return {
        "status": "COMMITTED",
        "repository": repository,
        "branch": work_branch,
        "base_branch": str(settings.coding_github_base_branch or "main"),
        "path": normalized,
        "commit_sha": commit_sha,
        "commit_url": commit.get("html_url"),
        "content_url": (result.get("content") or {}).get("html_url"),
        "ci": "PENDING",
        "message": "File committed to the isolated Coding Agent branch. Check the linked GitHub Actions run before reporting tests/build as passed.",
    }


async def commit_files_atomically(
    files: list[dict[str, Any]],
    *,
    branch: str,
    message: str,
    expected_base_sha: str,
) -> dict[str, Any]:
    """Commit a complete patch in one Git commit on an isolated branch."""
    _, repository, base_branch, _ = _validate_configuration()
    chosen_branch = validate_work_branch(branch)
    commit_message = str(message or "").strip()
    if not commit_message or len(commit_message) > 180 or "\n" in commit_message or "\r" in commit_message:
        raise CodingWorkspaceError("Commit message must be a single line of 1 to 180 characters.", 400)
    if not isinstance(files, list) or not files or len(files) > 5:
        raise CodingWorkspaceError("A coding patch must change between 1 and 5 files.", 400)

    current_base_sha = await get_branch_head_sha(base_branch)
    if current_base_sha != str(expected_base_sha or ""):
        raise CodingWorkspaceError(
            "The base branch changed after the patch was planned. Re-plan against the latest code before applying.",
            409,
        )
    branch_name, branch_sha = await _ensure_work_branch(chosen_branch)
    if branch_sha != current_base_sha:
        raise CodingWorkspaceError(
            "This Coding Agent branch already contains commits. Create a fresh plan/branch instead of overwriting existing work.",
            409,
        )

    base_commit = await _request(
        "GET", _repo_path(repository, "/git/commits/" + quote(current_base_sha, safe=""))
    )
    base_tree_sha = str(((base_commit.get("tree") or {}).get("sha")) or "")
    if not base_tree_sha:
        raise CodingWorkspaceError("GitHub base commit did not return a tree SHA.", 502)

    tree_entries: list[dict[str, str]] = []
    changed_paths: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            raise CodingWorkspaceError("Coding patch contains an invalid file entry.", 400)
        path = validate_workspace_path(str(item.get("path") or ""))
        content = item.get("content")
        if not isinstance(content, str) or len(content.encode("utf-8")) > _MAX_FILE_BYTES:
            raise CodingWorkspaceError("A changed file is empty/invalid or exceeds the 250 KB limit.", 413)
        if path in changed_paths:
            raise CodingWorkspaceError("Coding patch contains a duplicate file path.", 400)
        changed_paths.append(path)
        blob = await _request("POST", _repo_path(repository, "/git/blobs"), json_body={
            "content": content,
            "encoding": "utf-8",
        })
        blob_sha = str(blob.get("sha") or "")
        if not blob_sha:
            raise CodingWorkspaceError("GitHub did not return a blob SHA for " + path, 502)
        tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})

    tree = await _request("POST", _repo_path(repository, "/git/trees"), json_body={
        "base_tree": base_tree_sha,
        "tree": tree_entries,
    })
    tree_sha = str(tree.get("sha") or "")
    if not tree_sha:
        raise CodingWorkspaceError("GitHub did not return a tree SHA for the proposed patch.", 502)
    commit = await _request("POST", _repo_path(repository, "/git/commits"), json_body={
        "message": commit_message,
        "tree": tree_sha,
        "parents": [branch_sha],
    })
    commit_sha = str(commit.get("sha") or "")
    if not commit_sha:
        raise CodingWorkspaceError("GitHub did not return a commit SHA for the proposed patch.", 502)

    updated = await _request(
        "PATCH",
        _repo_path(repository, "/git/refs/heads/" + quote(branch_name, safe="/")),
        json_body={"sha": commit_sha, "force": False},
    )
    updated_sha = str((updated.get("object") or {}).get("sha") or "")
    if updated_sha != commit_sha:
        raise CodingWorkspaceError("GitHub did not confirm the isolated branch update.", 502)
    return {
        "status": "COMMITTED",
        "repository": repository,
        "branch": branch_name,
        "base_branch": base_branch,
        "base_sha": current_base_sha,
        "commit_sha": commit_sha,
        "commit_url": commit.get("html_url"),
        "changed_files": changed_paths,
        "ci": "PENDING",
    }


async def create_pull_request(
    branch: str,
    *,
    title: str,
    body: str,
) -> dict[str, Any]:
    """Open or reuse a PR for an isolated Coding Agent branch."""
    _, repository, base_branch, _ = _validate_configuration()
    head_branch = validate_work_branch(branch)
    clean_title = str(title or "").strip()[:240]
    if not clean_title:
        raise CodingWorkspaceError("Pull request title is required.", 400)
    owner = repository.split("/", 1)[0]
    endpoint = _repo_path(repository, "/pulls")
    existing = await _request(
        "GET",
        endpoint + "?state=open&head=" + quote(owner + ":" + head_branch, safe="") +
        "&base=" + quote(base_branch, safe=""),
    )
    if isinstance(existing, list) and existing:
        row = existing[0]
        if isinstance(row, dict):
            return {
                "status": "EXISTING",
                "number": row.get("number"),
                "url": row.get("html_url"),
                "title": row.get("title"),
                "state": row.get("state"),
                "branch": head_branch,
                "base_branch": base_branch,
            }
    result = await _request("POST", endpoint, json_body={
        "title": clean_title,
        "head": head_branch,
        "base": base_branch,
        "body": str(body or "")[:20000],
        "draft": False,
    })
    return {
        "status": "OPENED",
        "number": result.get("number"),
        "url": result.get("html_url"),
        "title": result.get("title"),
        "state": result.get("state"),
        "branch": head_branch,
        "base_branch": base_branch,
    }


async def get_commit_checks(commit_sha: str) -> dict[str, Any]:
    _, repository, _, _ = _validate_configuration()
    sha = str(commit_sha or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", sha):
        raise CodingWorkspaceError("Provide a valid commit SHA.", 400)
    checks = await _request("GET", _repo_path(repository, "/commits/" + quote(sha, safe="") + "/check-runs?per_page=50"))
    status = await _request("GET", _repo_path(repository, "/commits/" + quote(sha, safe="") + "/status"))
    rows = checks.get("check_runs") if isinstance(checks.get("check_runs"), list) else []
    conclusion_values = [str(row.get("conclusion") or "").lower() for row in rows if row.get("status") == "completed"]
    combined_state = str(status.get("state") or "").lower()
    if combined_state in {"failure", "error"} or any(
        value in {"failure", "cancelled", "timed_out", "action_required"} for value in conclusion_values
    ):
        overall = "FAILED"
    elif rows and all(
        row.get("status") == "completed" and str(row.get("conclusion") or "").lower() in {"success", "neutral", "skipped"}
        for row in rows
    ):
        overall = "PASSED"
    elif not rows and combined_state == "success":
        overall = "PASSED"
    else:
        overall = "RUNNING"
    return {
        "status": overall,
        "repository": _configuration()[1],
        "commit_sha": sha,
        "checks": [{
            "name": row.get("name"),
            "status": row.get("status"),
            "conclusion": row.get("conclusion"),
            "details_url": row.get("details_url") or row.get("html_url"),
        } for row in rows],
        "combined_status": status.get("state"),
        "combined_status_url": status.get("url"),
    }
