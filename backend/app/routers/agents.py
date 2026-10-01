from fastapi import APIRouter, Depends
from ..dependencies import get_current_user
from ..agents.registry import AGENTS
from ..orchestration.planner import build_plan

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("")
def list_agents(current_user=Depends(get_current_user)):
    return [
        {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "capabilities": list(agent.capabilities),
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
