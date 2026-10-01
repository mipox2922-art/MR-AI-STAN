from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import ActivityLog, Task
from ..routers.system import system_status
from ..tools.registry import registry_summary
from ..tools.router import route_command\nfrom .handoffs import build_browser_handoff


def _task_payload(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "progress": task.progress,
        "agent": task.agent,
        "result": task.result,
        "error": task.error,
    }


async def execute_mission(
    request: str,
    user: Any,
    db: Session,
) -> dict[str, Any]:
    """Execute only capabilities that have a verified backend hand.

    External browser/device/Gmail/coding actions stay explicitly WAITING_FOR_HAND.
    This prevents the Orchestrator from claiming work that another permissioned
    integration has not actually performed.
    """
    from .planner import build_plan

    plan = build_plan(request)
    mission = Task(
        user_id=user.id,
        title=request[:255],
        description="Mission created by MR AI Orchestrator",
        status="IN_PROGRESS",
        priority="NORMAL",
        agent="orchestrator",
        progress=0,
    )
    db.add(mission)
    db.add(ActivityLog(
        user_id=user.id,
        action="MISSION_STARTED",
        details=request[:500],
    ))
    db.commit()
    db.refresh(mission)

    steps = []
    for index, step in enumerate(plan["steps"], start=1):
        agent_id = step["agent"]
        if agent_id == "orchestrator" and "system_telemetry" in step["tools"]:
            result = system_status(user)
            steps.append({
                "step": index,
                "agent": agent_id,
                "tool": "system_telemetry",
                "status": "COMPLETED",
                "verified": True,
                "evidence": result,
            })
            continue

        route = route_command(request)
        tool_id = route.get("tool")

        if agent_id == "browser" and "browser_hands" in step["tools"]:
            handoff = build_browser_handoff(request)
            if handoff:
                steps.append({
                    "step": index,
                    "agent": agent_id,
                    "tool": "browser_hands",
                    "status": "WAITING_FOR_HAND",
                    "verified": False,
                    "handoff": handoff,
                    "evidence": {
                        "message": "Browser Agent prepared an explicit browser handoff for the connected extension.",
                    },
                })
                continue
        if tool_id == "searxng" and "searxng" in step["tools"]:
            if not registry_summary()["tools"]:
                status = "NOT_CONNECTED"
                evidence = {"message": "Search registry is unavailable."}
            else:
                # Search execution stays in the normal tool dispatch route. The
                # mission reports ownership but does not duplicate the HTTP action.
                status = "WAITING_FOR_HAND"
                evidence = {
                    "message": "Research Agent selected SearXNG; use the research tool dispatch to execute the search.",
                }
            steps.append({
                "step": index,
                "agent": agent_id,
                "tool": tool_id,
                "status": status,
                "verified": False,
                "evidence": evidence,
            })
            continue

        steps.append({
            "step": index,
            "agent": agent_id,
            "tool": step["tools"][0] if step["tools"] else None,
            "status": "WAITING_FOR_HAND",
            "verified": False,
            "evidence": {
                "message": "Selected agent has no connected execution hand for this mission in the backend.",
            },
        })

    finished = all(step["status"] == "COMPLETED" for step in steps)
    mission.status = "COMPLETED" if finished else "WAITING"
    mission.progress = 100 if finished else int(
        sum(step["status"] == "COMPLETED" for step in steps)
        / max(1, len(steps))
        * 100
    )
    mission.result = str({
        "steps": len(steps),
        "completed": sum(step["status"] == "COMPLETED" for step in steps),
        "waiting": sum(step["status"] == "WAITING_FOR_HAND" for step in steps),
    })
    db.add(ActivityLog(
        user_id=user.id,
        action="MISSION_COMPLETED" if finished else "MISSION_WAITING",
        details=f"Mission {mission.id}: {mission.status}",
    ))
    db.commit()
    db.refresh(mission)

    return {
        "status": mission.status,
        "mission": _task_payload(mission),
        "plan": plan,
        "steps": steps,
        "next_action": (
            "Mission verified complete."
            if finished
            else "Connect the required permissioned hands, then resume the waiting steps."
        ),
    }
