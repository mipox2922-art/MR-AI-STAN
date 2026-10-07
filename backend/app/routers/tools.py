from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..dependencies import get_current_user
from ..tools.registry import registry_summary
from ..tools.router import route_command
from ..routers.system import system_status
from ..models import ActivityLog
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

    if not settings.searxng_url:
        return {
            "status": "NOT_CONNECTED",
            "query": query,
            "results": [],
            "message": "Configure SEARXNG_URL to connect a self-hosted SearXNG instance.",
        }

    endpoint = settings.searxng_url.rstrip("/") + "/search"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(
                endpoint,
                params={"q": query, "format": "json"},
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"SearXNG search failed: {type(exc).__name__}")

    results = []
    for item in data.get("results", [])[:20]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "engine": item.get("engine", ""),
        })

    return {
        "status": "COMPLETED",
        "query": query,
        "results": results,
        "source": "configured_searxng",
    }


@router.post("/route")
def route_tool(
    payload: dict[str, Any],
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    command = str(payload.get("command", "")).strip()
    if not command:
        raise HTTPException(status_code=400, detail="command is required")
    return route_command(command)

async def _search_searxng(query: str) -> dict[str, Any]:
    if not settings.searxng_url:
        return {
            "status": "NOT_CONNECTED",
            "query": query,
            "results": [],
            "message": "Configure SEARXNG_URL to connect a self-hosted SearXNG instance.",
        }

    endpoint = settings.searxng_url.rstrip("/") + "/search"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(
                endpoint,
                params={"q": query, "format": "json"},
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"SearXNG search failed: {type(exc).__name__}")

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "engine": item.get("engine", ""),
        }
        for item in data.get("results", [])[:20]
    ]
    return {
        "status": "COMPLETED",
        "query": query,
        "results": results,
        "source": "configured_searxng",
    }

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
            details=f"searxng: {command[:180]}",
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
