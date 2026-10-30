from __future__ import annotations

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..connectors.coding_agent import (
    apply_coding_plan,
    coding_agent_status,
    plan_coding_task,
    verify_coding_plan,
)
from ..connectors.coding_workspace import (
    CodingWorkspaceError,
    get_commit_checks,
    inspect_files,
    write_file,
)
from ..dependencies import get_current_user
from ..tools.registry import registry_summary
from ..tools.router import route_command
from ..routers.system import system_status
from ..models import ActivityLog, Task, TaskStep
from ..database import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/tools", tags=["Tools"])

@router.get("")
def list_tools(current_user=Depends(get_current_user)) -> dict[str, Any]:
    return registry_summary()

@router.post("/search")
async def search_web(payload: dict[str, Any], current_user=Depends(get_current_user)) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    result = await _search_searxng(query)
    if result.get("status") == "COMPLETED":
        return result
    raise HTTPException(
        status_code=502,
        detail={
            "message": result.get("message", "Web search did not return results."),
            "query": query,
            "source": result.get("source"),
            "fallback_status": result.get("status"),
        },
    )


@router.get("/coding/status")
def coding_status(current_user=Depends(get_current_user)) -> dict[str, Any]:
    """Report the actual configured Coding Agent workspace, never a guessed READY state."""
    return coding_agent_status()


@router.post("/coding/inspect")
async def coding_inspect(
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    paths = payload.get("paths")
    branch = payload.get("branch")
    try:
        return await inspect_files(paths, branch=branch)
    except CodingWorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.put("/coding/files/{file_path:path}")
async def coding_write_file(
    file_path: str,
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    content = payload.get("content")
    message = payload.get("message")
    if not isinstance(content, str) or not isinstance(message, str):
        raise HTTPException(status_code=422, detail="content and message must both be strings.")
    try:
        result = await write_file(file_path, content, message)
    except CodingWorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    db.add(ActivityLog(
        user_id=current_user.id,
        action="CODING_WORKSPACE_FILE_COMMITTED",
        details=f"repo={result['repository']}; branch={result['branch']}; path={result['path']}; commit={result['commit_sha']}",
    ))
    db.commit()
    return result


@router.post("/coding/agent/plan")
async def coding_agent_plan(
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    request_text = str(payload.get("request") or "").strip()
    try:
        result = await plan_coding_task(request_text)
    except CodingWorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    plan = result.get("plan") or {}
    db.add(ActivityLog(
        user_id=current_user.id,
        action="CODING_AGENT_PLAN_CREATED",
        details=(
            f"plan_id={plan.get('plan_id')}; provider={plan.get('provider')}; "
            f"files_reviewed={len(plan.get('files_reviewed') or [])}; "
            f"changes_proposed={len(plan.get('changes') or [])}; no_write=true"
        ),
    ))
    db.commit()
    return result


@router.post("/coding/agent/apply")
async def coding_agent_apply(
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    plan = payload.get("plan")
    signature = payload.get("proposal_signature")
    try:
        safe_plan = verify_coding_plan(plan, signature)
    except CodingWorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    # Repeated clicks are idempotent: never create duplicate commits/PRs for one signed proposal.
    previous_tasks = (
        db.query(Task)
        .filter(Task.user_id == current_user.id, Task.agent == "coding", Task.source == "coding_agent")
        .order_by(Task.id.desc())
        .limit(100)
        .all()
    )
    for previous in previous_tasks:
        try:
            saved = json.loads(previous.result or "{}")
        except (TypeError, ValueError):
            saved = {}
        if saved.get("plan_id") == safe_plan.get("plan_id"):
            return {**saved, "task_id": previous.id, "idempotent": True}

    try:
        result = await apply_coding_plan(plan, signature)
    except CodingWorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    task = Task(
        user_id=current_user.id,
        title=("Coding Agent: " + str(result.get("summary") or safe_plan.get("summary") or "Code change"))[:255],
        description=str(safe_plan.get("request") or "")[:12000],
        status="WAITING_FOR_HAND" if result.get("status") == "COMMITTED_NO_PR" else "IN_PROGRESS",
        priority="NORMAL",
        agent="coding",
        source="coding_agent",
        requested_by=str(getattr(current_user, "username", None) or "Boss Ferisi")[:100],
        approved_by=current_user.id,
        progress=15 if result.get("status") == "COMMITTED_NO_PR" else 25,
        error=str(result.get("message") or "") if result.get("status") == "COMMITTED_NO_PR" else None,
        result=json.dumps(result, ensure_ascii=False, default=str),
    )
    db.add(task)
    db.flush()
    result["task_id"] = task.id
    step = TaskStep(
        task_id=task.id,
        position=1,
        title="Patch committed; verify GitHub Actions CI",
        state="pending",
        evidence=json.dumps({
            "commit_sha": result.get("commit_sha"),
            "branch": result.get("branch"),
            "pull_request": (result.get("pull_request") or {}).get("url"),
            "checks": "PENDING",
            "tests_to_run": result.get("tests_to_run") or [],
        }, ensure_ascii=False),
    )
    db.add(step)
    task.result = json.dumps(result, ensure_ascii=False, default=str)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="CODING_AGENT_PR_OPENED",
        details=(
            f"task_id={task.id}; plan_id={result.get('plan_id')}; branch={result.get('branch')}; "
            f"commit={result.get('commit_sha')}; pr={(result.get('pull_request') or {}).get('number')}"
        ),
    ))
    db.commit()
    db.refresh(task)
    return result


@router.get("/coding/agent/checks/{commit_sha}")
async def coding_agent_checks(
    commit_sha: str,
    task_id: int | None = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        checks = await get_commit_checks(commit_sha)
    except CodingWorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if task_id is None:
        return checks
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.user_id == current_user.id,
        Task.agent == "coding",
        Task.source == "coding_agent",
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Coding Agent task not found.")
    try:
        result = json.loads(task.result or "{}")
    except (TypeError, ValueError):
        result = {}
    if str(result.get("commit_sha") or "").lower() != str(commit_sha).lower():
        raise HTTPException(status_code=409, detail="Commit SHA does not match this Coding Agent task.")

    step = db.query(TaskStep).filter(TaskStep.task_id == task.id).order_by(TaskStep.position.asc()).first()
    if step is None:
        step = TaskStep(task_id=task.id, position=1, title="Verify GitHub Actions CI", state="pending")
        db.add(step)

    evidence = {
        "commit_sha": commit_sha,
        "branch": result.get("branch"),
        "pull_request": (result.get("pull_request") or {}).get("url"),
        "ci_status": checks.get("status"),
        "combined_status": checks.get("combined_status"),
        "checks": checks.get("checks") or [],
        "tests_to_run": result.get("tests_to_run") or [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if checks.get("status") == "PASSED":
        task.status = "COMPLETED"
        task.progress = 100
        task.error = None
        step.state = "verified"
        step.verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
        evidence["message"] = "GitHub Actions checks for this commit completed successfully."
    elif checks.get("status") == "FAILED":
        failed = [
            str(item.get("name") or "check")
            for item in (checks.get("checks") or [])
            if str(item.get("conclusion") or "").lower() in {"failure", "cancelled", "timed_out", "action_required"}
        ]
        task.status = "FAILED"
        task.progress = 25
        task.error = "GitHub Actions checks failed: " + (", ".join(failed[:5]) or "combined commit status is not successful")
        step.state = "failed"
        step.verified_at = None
        evidence["message"] = task.error
    else:
        task.status = "IN_PROGRESS"
        task.progress = 55
        step.state = "pending"
        evidence["message"] = "GitHub Actions checks are still running or have not reported a final result."
    step.evidence = json.dumps(evidence, ensure_ascii=False, default=str)
    result["ci"] = checks.get("status")
    result["checks"] = checks
    task.result = json.dumps(result, ensure_ascii=False, default=str)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="CODING_AGENT_CI_CHECKED",
        details=f"task_id={task.id}; commit={commit_sha}; status={checks.get('status')}",
    ))
    db.commit()
    return {**checks, "task": {"id": task.id, "status": task.status, "progress": task.progress, "error": task.error}}


@router.get("/coding/checks/{commit_sha}")
async def coding_commit_checks(
    commit_sha: str,
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await get_commit_checks(commit_sha)
    except CodingWorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/route")
def route_tool(
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    command = str(payload.get("command", "")).strip()
    if not command:
        raise HTTPException(status_code=400, detail="command is required")
    return route_command(command)

class _DuckDuckGoResultsParser(HTMLParser):
    """Parse only standard result links/snippets from DuckDuckGo's HTML endpoint."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._mode: str | None = None
        self._title_depth = 0
        self._snippet_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(str(attrs.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            raw_url = str(attrs.get("href") or "").strip()
            parsed = urlparse(raw_url)
            if parsed.hostname and parsed.hostname.lower().endswith("duckduckgo.com"):
                target = parse_qs(parsed.query).get("uddg", [""])[0]
            else:
                target = raw_url
            target_parsed = urlparse(target)
            if target_parsed.scheme in {"http", "https"} and target_parsed.hostname:
                self.results.append({"title": "", "url": target, "content": ""})
                self._mode = "title"
                self._title_depth = 1
        elif self.results and "result__snippet" in classes:
            self._mode = "snippet"
            self._snippet_depth = 1
        elif self._mode == "title":
            self._title_depth += 1
        elif self._mode == "snippet":
            self._snippet_depth += 1

    def handle_endtag(self, tag):
        if self._mode == "title":
            self._title_depth -= 1
            if self._title_depth <= 0:
                self._mode = None
        elif self._mode == "snippet":
            self._snippet_depth -= 1
            if self._snippet_depth <= 0:
                self._mode = None

    def handle_data(self, data):
        if not self.results or not str(data).strip():
            return
        if self._mode == "title":
            self.results[-1]["title"] += str(data)
        elif self._mode == "snippet":
            self.results[-1]["content"] += str(data)


async def _search_duckduckgo_html(query: str) -> dict[str, Any]:
    """Free no-key fallback; sends only the search query to DuckDuckGo."""
    parser = _DuckDuckGoResultsParser()
    try:
        async with httpx.AsyncClient(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "MR-AI-STAN/1.0 (public web research)"},
        ) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
            )
            response.raise_for_status()
            parser.feed(response.text)
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "status": "NOT_CONNECTED",
            "query": query,
            "results": [],
            "source": "duckduckgo_html",
            "message": f"Built-in web search failed: {type(exc).__name__}.",
        }

    results = [
        {
            "title": item["title"].strip()[:500],
            "url": item["url"],
            "content": item["content"].strip()[:2000],
            "engine": "duckduckgo",
        }
        for item in parser.results
        if item.get("title", "").strip() and item.get("url")
    ][:20]
    return {
        "status": "COMPLETED" if results else "NO_RESULTS",
        "query": query,
        "results": results,
        "source": "duckduckgo_html",
        "message": None if results else "DuckDuckGo returned no parseable public search results.",
    }


async def _search_searxng(query: str) -> dict[str, Any]:
    """Prefer configured SearXNG, then use the built-in no-key public search fallback."""
    primary_error = None
    if settings.searxng_url:
        endpoint = settings.searxng_url.rstrip("/") + "/search"
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(endpoint, params={"q": query, "format": "json"})
                response.raise_for_status()
                data = response.json()
            results = [
                {
                    "title": str(item.get("title") or "")[:500],
                    "url": str(item.get("url") or ""),
                    "content": str(item.get("content") or "")[:2000],
                    "engine": str(item.get("engine") or ""),
                }
                for item in data.get("results", [])[:20]
                if isinstance(item, dict)
                and urlparse(str(item.get("url") or "")).scheme in {"http", "https"}
                and urlparse(str(item.get("url") or "")).hostname
            ]
            if results:
                return {"status": "COMPLETED", "query": query, "results": results, "source": "configured_searxng"}
            primary_error = "SearXNG returned no usable results"
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            primary_error = f"SearXNG failed: {type(exc).__name__}"

    fallback = await _search_duckduckgo_html(query)
    fallback["primary_source"] = "configured_searxng" if settings.searxng_url else None
    fallback["fallback_used"] = True
    if primary_error:
        fallback["source_warnings"] = [primary_error]
    if fallback.get("status") == "COMPLETED":
        return fallback
    fallback["status"] = "NOT_CONNECTED"
    fallback["message"] = (
        "SearXNG and built-in DuckDuckGo search did not return usable results. "
        "No research result is claimed."
    )
    return fallback

@router.post("/dispatch")
async def dispatch_tool(
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    command = str(payload.get("command", "")).strip()
    if not command:
        raise HTTPException(status_code=400, detail="command is required")

    route = route_command(command)
    if route["status"] == "NO_TOOL_MATCH":
        return route

    tool_id = route["tool"]
    if tool_id == "coding":
        workspace = coding_workspace_status()
        if not workspace.get("configured"):
            return {
                "status": "NOT_CONNECTED",
                "route": route,
                "workspace": workspace,
                "message": "Coding Agent imesimamishwa kwa sababu GitHub workspace credential haijawekwa. Hakuna file iliyobadilishwa.",
            }
        return {
            "status": "WAITING_FOR_PARAMETERS",
            "route": route,
            "workspace": workspace,
            "message": "GitHub Coding Workspace imeunganishwa. Toa file path/content yenyewe kwa endpoint ya /tools/coding/files/{path}; test/build status itachukuliwa kutoka GitHub Actions, si kubuniwa na agent.",
        }

    if tool_id == "system_telemetry":
        result = system_status(current_user)
        db.add(ActivityLog(
            user_id=current_user.id,
            action="TOOL_DISPATCH",
            details="system_telemetry",
        ))
        db.commit()
        return {"status": "COMPLETED", "route": route, "result": result}

    if tool_id == "scheduler":
        return {
            "status": "WAITING_FOR_PARAMETERS",
            "route": route,
            "message": "Scheduler selected. Use the /scheduler endpoint with title, command and run_at; an incomplete chat command will not create a schedule.",
        }

    if tool_id == "searxng":
        result = await _search_searxng(command)
        db.add(ActivityLog(
            user_id=current_user.id,
            action="TOOL_DISPATCH",
            details=f"searxng: query_length={len(command)}",
        ))
        db.commit()
        return {"status": result["status"], "route": route, "result": result}

    if tool_id in {"browser_hands", "device_bridge", "coding", "gmail", "creative_canvas", "security", "tesseract", "ffmpeg", "whisper_local", "openstreetmap", "scheduler", "memory"}:
        return {
            "status": "WAITING_FOR_HAND",
            "route": route,
            "message": f"Tool {tool_id} is selected, but its permissioned execution hand is not connected to this dispatch route yet.",
        }

    return {"status": "UNSUPPORTED", "route": route}
