import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog, ApprovalRequest, Task
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
            "capability_count": len(agent.tools),
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


@router.post("/mission/{mission_id}/start")
async def start_approved_mission(
    mission_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mission = db.query(Task).filter(
        Task.id == mission_id,
        Task.user_id == current_user.id,
        Task.agent == "orchestrator",
    ).first()
    if not mission:
        raise HTTPException(404, "Mission not found")
    if mission.approved_by != current_user.id or mission.status != "PENDING":
        raise HTTPException(403, "Boss approval is required before this mission can execute")
    return await execute_mission(mission.description or mission.title, current_user, db, mission=mission)


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

    if mission.agent != "orchestrator" or mission.status not in {"WAITING", "IN_PROGRESS", "WAITING_FOR_HAND"}:
        raise HTTPException(409, "Only an active orchestrated mission can accept a handoff.")

    reported_status = str(payload.get("status", "")).upper()
    evidence = payload.get("evidence")
    if reported_status not in {"COMPLETED", "FAILED"}:
        raise HTTPException(400, "handoff status must be COMPLETED or FAILED")

    # Browser/device handoffs originate outside the backend. A client-supplied
    # status or evidence blob is not independent proof that the remote action worked.
    if reported_status == "COMPLETED":
        status = "WAITING_FOR_VERIFICATION"
        mission.status = status
        mission.progress = min(99, mission.progress or 0)
        mission.error = (
            "The hand reported completion, but the backend cannot independently verify "
            "the remote browser/device outcome yet."
        )
    else:
        status = "FAILED"
        mission.status = status
        mission.error = str(evidence)[:4000] if evidence is not None else "The execution hand reported failure."

    try:
        mission.result = json.dumps(evidence, ensure_ascii=False, default=str)[:12000]
    except (TypeError, ValueError):
        mission.result = str(evidence)[:12000]

    db.add(ActivityLog(
        user_id=current_user.id,
        action="MISSION_HANDOFF_RESULT",
        details=f"Mission {mission.id}: reported={reported_status}; stored={status}",
    ))
    db.commit()
    db.refresh(mission)

    return {
        "status": status,
        "reported_status": reported_status,
        "verified": False,
        "next_action": (
            "The handoff is waiting for independent verification. The mission has not been marked completed."
            if status == "WAITING_FOR_VERIFICATION"
            else "Review the failed handoff evidence and retry only after correcting the cause."
        ),
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
        agent_id = str(payload.get("agent", "orchestrator")).strip() or "orchestrator"
        task = Task(
            user_id=current_user.id, title=title,
            description=str(payload.get("description", "")).strip(),
            priority=str(payload.get("priority", "NORMAL")).upper(),
            agent=agent_id, status="WAITING_APPROVAL", source="agent",
            requested_by=f"agent:{agent_id}", progress=0,
        )
        db.add(task)
        db.flush()
        approval = ApprovalRequest(
            user_id=current_user.id, action="AGENT_TASK_PROPOSAL",
            payload=json.dumps({"task_id": task.id, "agent": agent_id}, ensure_ascii=False),
            status="PENDING",
        )
        db.add(approval)
        db.add(ActivityLog(user_id=current_user.id, action="AGENT_TASK_PROPOSED",
            details=f"task_id={task.id}; source=agent"))
        db.commit()
        db.refresh(task)
        db.refresh(approval)
        return {
            "status": "WAITING_APPROVAL", "action": action, "approval_id": approval.id,
            "message": "Wakala amependekeza kazi; haijaanza kutekelezwa. Boss Ferisi lazima aidhinishe.",
            "result": {"task_id": task.id, "title": task.title, "agent": task.agent,
                "status": task.status, "source": task.source},
        }

    if action in {"browser", "device", "gmail", "creative", "coding"}:
        return {
            "status": "WAITING_FOR_HAND",
            "action": action,
            "message": "This action requires the corresponding permissioned external hand. No completion is claimed.",
        }

    raise HTTPException(400, "Unsupported agent action")
