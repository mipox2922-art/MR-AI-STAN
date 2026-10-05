from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..models import ActivityLog, Task
from ..routers.system import system_status
from ..tools.registry import registry_summary
from ..agents.registry import AGENTS


ACTIVE_TASK_STATES = {"IN_PROGRESS", "RUNNING", "WORKING", "STARTED"}
WAITING_TASK_STATES = {"PENDING", "WAITING", "BLOCKED"}


def build_executive_briefing(user: Any, db: Session) -> dict[str, Any]:
    """Build a truthful JARVIS-style operational briefing from persisted state."""
    now = datetime.utcnow()

    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id)
        .order_by(Task.id.desc())
        .limit(200)
        .all()
    )
    activities = (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == user.id)
        .order_by(ActivityLog.id.desc())
        .limit(12)
        .all()
    )

    status_counts = Counter((task.status or "PENDING").upper() for task in tasks)
    agent_tasks: dict[str, list[Task]] = {}
    for task in tasks:
        agent_id = (task.agent or "orchestrator").strip() or "orchestrator"
        agent_tasks.setdefault(agent_id, []).append(task)

    fleet = []
    for definition in AGENTS:
        assigned = agent_tasks.get(definition.id, [])
        states = {(task.status or "PENDING").upper() for task in assigned}
        if states & ACTIVE_TASK_STATES:
            state = "WORKING"
        elif states & WAITING_TASK_STATES:
            state = "WAITING"
        elif any((task.status or "").upper() == "COMPLETED" for task in assigned):
            state = "IDLE"
        else:
            state = "READY"

        latest = assigned[0] if assigned else None
        fleet.append({
            "id": definition.id,
            "name": definition.name,
            "status": state,
            "risk": definition.risk,
            "tools": list(definition.tools),
            "current_task": (
                {
                    "id": latest.id,
                    "title": latest.title,
                    "status": latest.status,
                    "progress": latest.progress,
                }
                if latest and state in {"WORKING", "WAITING"}
                else None
            ),
            "last_result": latest.result if latest and latest.status == "COMPLETED" else None,
        })

    system = system_status(user)
    tool_summary = registry_summary()

    recent = []
    for item in activities:
        recent.append({
            "id": item.id,
            "action": item.action,
            "details": item.details,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })

    working_count = sum(agent["status"] == "WORKING" for agent in fleet)
    waiting_count = sum(agent["status"] == "WAITING" for agent in fleet)

    # Deliberately explicit: financial/social integrations do not exist in the
    # current backend, so the briefing must not invent earnings or publications.
    financial = {
        "status": "NOT_CONNECTED",
        "message": "No verified financial integration is connected.",
    }
    social = {
        "status": "NOT_CONNECTED",
        "message": "No verified social publishing integration is connected.",
    }

    blockers = []
    if tool_summary.get("not_connected", 0) or tool_summary.get("optional", 0):
        blockers.append({
            "type": "TOOL_CONNECTIVITY",
            "message": "Some capabilities are not connected or installed yet.",
        })

    failed = status_counts.get("FAILED", 0) + status_counts.get("ERROR", 0)
    if failed:
        blockers.append({
            "type": "TASK_FAILURES",
            "message": f"{failed} task(s) are recorded as FAILED/ERROR and need review.",
        })

    return {
        "status": "COMPLETED",
        "generated_at": now.isoformat(),
        "system": system,
        "agents": {
            "total": len(fleet),
            "working": working_count,
            "waiting": waiting_count,
            "fleet": fleet,
        },
        "tasks": {
            "total": len(tasks),
            "completed": status_counts.get("COMPLETED", 0),
            "working": sum(status_counts[state] for state in ACTIVE_TASK_STATES),
            "waiting": sum(status_counts[state] for state in WAITING_TASK_STATES),
            "failed": failed,
            "counts": dict(status_counts),
        },
        "recent_activity": recent,
        "financial": financial,
        "social": social,
        "discoveries": [],
        "blockers": blockers,
        "next_action": (
            "Review active/waiting missions first."
            if working_count or waiting_count
            else "Command Center is ready for the next Boss mission."
        ),
        "truth_boundary": [
            "Completion is reported only from persisted task/tool evidence.",
            "Financial results are unavailable until a verified financial integration exists.",
            "Social publication is unavailable until an authorized publishing integration exists.",
            "Missing data is reported as unavailable instead of being invented.",
        ],
    }
