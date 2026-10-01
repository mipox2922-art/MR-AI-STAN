from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog, Task
from ..routers.system import system_status
from ..agents.registry import AGENTS
from ..orchestration.planner import build_plan
from ..orchestration.briefing import build_executive_briefing
from ..orchestration.executor import execute_mission

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("")
def list_agents(current_user=Depends(get_current_user)):
    return [
        {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "capabilities": list(agent.capabilities),
            "tools": list(agent.tools),
            "risk": agent.risk,
        }
        for agent in AGENTS
    ]


@router.post("/plan")
def plan_agent_work(payload: dict, current_user=Depends(get_current_user)):
    request = str(payload.get("request", "")).strip()
    if not request:
        return {"status": "REJECTED", "reason": "request is required"}
    return build_plan(request)


@router.get("/briefing")
def executive_briefing(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_executive_briefing(current_user, db)


@router.post("/mission")
async def run_mission(
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request = str(payload.get("request", "")).strip()
    if not request:
        raise HTTPException(400, "request is required")
    return await execute_mission(request, current_user, db)


@router.post("/mission/{mission_id}/handoff")
def report_mission_handoff(
    mission_id: int,
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mission = (
        db.query(Task)
        .filter(Task.id == mission_id, Task.user_id == current_user.id)
        .first()
    )
    if not mission:
        raise HTTPException(404, "Mission not found")

    status = str(payload.get("status", "")).upper()
    evidence = payload.get("evidence")
    if status not in {"COMPLETED", "FAILED"}:
        raise HTTPException(400, "handoff status must be COMPLETED or FAILED")

    mission.status = status
    mission.progress = 100 if status == "COMPLETED" else mission.progress
    mission.result = str(evidence)[:12000] if evidence is not None else ""
    mission.error = None if status == "COMPLETED" else str(evidence)[:4000]
    db.add(ActivityLog(
        user_id=current_user.id,
        action="MISSION_HANDOFF_RESULT",
        details=f"Mission {mission.id}: {status}",
    ))
    db.commit()
    db.refresh(mission)

    return {
        "status": status,
        "verified": status == "COMPLETED",
        "mission": {
            "id": mission.id,
            "status": mission.status,
            "progress": mission.progress,
            "result": mission.result,
            "error": mission.error,
        },
    }


@router.post("/execute")
def execute_agent_action(
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Execute only first-party safe actions implemented by the backend.

    External browser/device actions are intentionally delegated to their
    permissioned local hands instead of being impersonated here.
    """
    action = str(payload.get("action", "")).strip().casefold()

    if action == "system_scan":
        result = system_status(current_user)
        db.add(ActivityLog(
            user_id=current_user.id,
            action="SYSTEM_SCAN",
            details="Verified host telemetry requested by orchestrator",
        ))
        db.commit()
        return {"status": "COMPLETED", "action": action, "result": result}

    if action == "create_task":
        title = str(payload.get("title", "")).strip()
        if not title:
            raise HTTPException(400, "title is required")
        task = Task(
            user_id=current_user.id,
            title=title,
            description=str(payload.get("description", "")).strip(),
            priority=str(payload.get("priority", "NORMAL")).upper(),
            agent=str(payload.get("agent", "orchestrator")).strip() or "orchestrator",
        )
        db.add(task)
        db.add(ActivityLog(
            user_id=current_user.id,
            action="AGENT_TASK_CREATED",
            details=title,
        ))
        db.commit()
        db.refresh(task)
        return {
            "status": "COMPLETED",
            "action": action,
            "result": {
                "task_id": task.id,
                "title": task.title,
                "agent": task.agent,
            },
        }

    if action in {"browser", "device", "gmail", "creative", "coding"}:
        return {
            "status": "WAITING_FOR_HAND",
            "action": action,
            "message": "This action requires the corresponding permissioned external hand. No completion is claimed.",
        }

    raise HTTPException(400, "Unsupported agent action")
