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
from ..research.public_sources import search_public_sources
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
    query = str(payload.get("query", "")).strip()[:300]
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    return await _search_searxng(query)


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
    """Extract standard result links/snippets without accepting non-web schemes."""

    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._mode: str | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(str(attrs.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            raw_url = str(attrs.get("href") or "").strip()
            parsed = urlparse(raw_url)
            if (
                (parsed.hostname and parsed.hostname.lower().endswith("duckduckgo.com"))
                or parsed.path.startswith("/l/")
            ):
                target = parse_qs(parsed.query).get("uddg", [""])[0]
            else:
                target = raw_url
            target_parsed = urlparse(target)
            if target_parsed.scheme in {"http", "https"} and target_parsed.hostname:
                self.results.append({"title": "", "url": target, "content": ""})
                self._mode = "title"
                self._depth = 1
                return
        if "result__snippet" in classes and self.results:
            self._mode = "snippet"
            self._depth = 1
            return
        if self._mode and tag not in self._VOID_TAGS:
            self._depth += 1

    def handle_endtag(self, tag):
        if not self._mode or tag in self._VOID_TAGS:
            return
        self._depth -= 1
        if self._depth <= 0:
            self._mode = None
            self._depth = 0

    def handle_data(self, data):
        if not self.results or not self._mode or not str(data).strip():
            return
        self.results[-1][self._mode] += str(data)


async def _search_duckduckgo_html(query: str) -> dict[str, Any]:
    """Free no-key search fallback; only the query is sent to DuckDuckGo."""
    parser = _DuckDuckGoResultsParser()
    try:
        async with httpx.AsyncClient(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "MR-AI-STAN/1.0 (public web research)"},
        ) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": str(query or "").strip()[:300]},
            )
            response.raise_for_status()
            parser.feed(response.text)
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "status": "NOT_CONNECTED",
            "query": query,
            "count": 0,
            "results": [],
            "sources": [],
            "source": "duckduckgo_html",
            "source_warnings": [f"DuckDuckGo: {type(exc).__name__}"],
        }

    results = [
        {
            "title": item["title"].strip()[:500],
            "url": item["url"],
            "content": item["content"].strip()[:2000],
            "engine": "duckduckgo",
            "source": "DuckDuckGo",
        }
        for item in parser.results
        if item.get("title", "").strip() and item.get("url")
    ][:20]
    return {
        "status": "COMPLETED" if results else "NO_RESULTS",
        "query": query,
        "count": len(results),
        "results": results,
        "sources": ["DuckDuckGo"] if results else [],
        "source": "duckduckgo_html",
        "source_warnings": [],
    }


async def _search_searxng(query: str) -> dict[str, Any]:
    """Search SearXNG, then DuckDuckGo, then bounded public read APIs."""
    normalized = str(query or "").strip()[:300]
    if not normalized:
        return {
            "status": "REJECTED",
            "query": normalized,
            "count": 0,
            "results": [],
            "sources": [],
            "source_warnings": ["Query is empty."],
        }

    warnings: list[str] = []
    if settings.searxng_url:
        endpoint = settings.searxng_url.rstrip("/") + "/search"
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(endpoint, params={"q": normalized, "format": "json"})
                response.raise_for_status()
                data = response.json()
            results = [
                {
                    "title": str(item.get("title") or "")[:500],
                    "url": str(item.get("url") or ""),
                    "content": str(item.get("content") or "")[:2000],
                    "engine": str(item.get("engine") or ""),
                    "source": str(item.get("engine") or "SearXNG"),
                }
                for item in (data.get("results") or [])[:20]
                if isinstance(item, dict)
                and urlparse(str(item.get("url") or "")).scheme in {"http", "https"}
                and urlparse(str(item.get("url") or "")).hostname
            ]
            if results:
                return {
                    "status": "COMPLETED",
                    "query": normalized,
                    "count": len(results),
                    "results": results,
                    "sources": ["SearXNG"],
                    "source": "configured_searxng",
                    "fallback_used": False,
                    "source_warnings": [],
                }
            warnings.append("SearXNG: no usable results")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            warnings.append(f"SearXNG: {type(exc).__name__}")

    duckduckgo = await _search_duckduckgo_html(normalized)
    if duckduckgo.get("status") == "COMPLETED" and duckduckgo.get("results"):
        duckduckgo["fallback_used"] = True
        duckduckgo["primary_source"] = "configured_searxng" if settings.searxng_url else None
        duckduckgo["source_warnings"] = warnings + (duckduckgo.get("source_warnings") or [])
        return duckduckgo
    warnings.extend(duckduckgo.get("source_warnings") or ["DuckDuckGo: no usable results"])

    # Last fallback uses two bounded, no-key public APIs. It is explicitly
    # limited to Wikipedia and Hacker News, not represented as full-web search.
    try:
        public_result = await search_public_sources(normalized, limit=20)
    except Exception as exc:
        public_result = {
            "status": "SOURCE_ERROR",
            "query": normalized,
            "count": 0,
            "results": [],
            "sources": [],
            "source_warnings": [f"Public APIs: {type(exc).__name__}"],
        }
    public_result["fallback_used"] = True
    public_result["primary_source"] = "configured_searxng" if settings.searxng_url else None
    public_result["secondary_source"] = "duckduckgo_html"
    public_result["source_warnings"] = warnings + (public_result.get("source_warnings") or [])
    if public_result.get("status") in {"COMPLETED", "NO_RESULTS"}:
        public_result["source"] = "public_api_fallback"
        return public_result

    public_result["status"] = "NOT_CONNECTED"
    public_result["message"] = (
        "SearXNG, DuckDuckGo and the limited public APIs did not return usable results. "
        "No research result is claimed."
    )
    return public_result


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
