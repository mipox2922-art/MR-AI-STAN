from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import ActivityLog, ApprovalRequest, Task, TaskStep
from ..routers.system import system_status
from ..tools.registry import registry_summary
from ..tools.router import route_command
from .handoffs import build_browser_handoff


def _task_payload(task: Task) -> dict[str, Any]:
    return {
        "id": task.id, "title": task.title, "status": task.status, "progress": task.progress,
        "agent": task.agent, "result": task.result, "error": task.error, "source": task.source,
        "requested_by": task.requested_by, "approved_by": task.approved_by,
    }


def _add_steps_from_plan(db: Session, task_id: int, plan: dict[str, Any]) -> list[TaskStep]:
    rows = []
    for index, spec in enumerate(plan.get("steps") or [], start=1):
        label = str(spec.get("name") or spec.get("agent") or f"Hatua {index}")[:255]
        row = TaskStep(task_id=task_id, position=index, title=label, state="pending")
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


async def execute_mission(
    request: str,
    user: Any,
    db: Session,
    mission: Task | None = None,
) -> dict[str, Any]:
    """Create an approval proposal first; execute only an already-approved mission."""
    from .planner import build_plan

    plan = build_plan(request)
    if mission is None:
        proposed = Task(
            user_id=user.id,
            title=request[:255],
            description=request,
            status="WAITING_APPROVAL",
            priority="NORMAL",
            agent="orchestrator",
            source="orchestrator",
            requested_by="MR AI Orchestrator",
            progress=0,
        )
        db.add(proposed)
        db.flush()
        _add_steps_from_plan(db, proposed.id, plan)
        approval = ApprovalRequest(
            user_id=user.id,
            action="MISSION_EXECUTION",
            payload=json.dumps({"task_id": proposed.id, "request": request[:6000]}, ensure_ascii=False),
            status="PENDING",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        db.add(approval)
        db.add(ActivityLog(
            user_id=user.id,
            action="MISSION_PROPOSED",
            details=f"task_id={proposed.id}; approval_id=pending; steps={len(plan.get('steps') or [])}",
        ))
        db.commit()
        db.refresh(proposed)
        db.refresh(approval)
        return {
            "status": "WAITING_APPROVAL",
            "mission": _task_payload(proposed),
            "approval_id": approval.id,
            "plan": plan,
            "steps": [{
                "step": index,
                "agent": item.get("agent", "Haijathibitishwa"),
                "name": item.get("name", item.get("agent", "Hatua")),
                "status": "WAITING_APPROVAL",
                "verified": False,
                "evidence": {"message": "Imependekezwa na Orchestrator; haijatekelezwa kabla ya idhini ya Boss."},
            } for index, item in enumerate(plan.get("steps") or [], start=1)],
            "next_action": "Boss Ferisi akague mpango kisha aidhinishe. Hakuna kitendo cha nje kilichotekelezwa.",
        }

    if mission.user_id != user.id or mission.agent != "orchestrator":
        return {"status": "REJECTED", "reason": "Mission owner/agent did not match."}
    if mission.approved_by != user.id or mission.status != "PENDING":
        return {"status": "WAITING_APPROVAL", "mission": _task_payload(mission),
                "next_action": "Boss approval is required before any mission step executes."}

    from ..models import TaskStep as StepModel
    db.query(StepModel).filter(StepModel.task_id == mission.id).delete(synchronize_session=False)
    mission.status = "IN_PROGRESS"
    mission.error = None
    mission.result = None
    mission.progress = 0
    db.add(ActivityLog(user_id=user.id, action="MISSION_STARTED", details=f"task_id={mission.id}; approved_by={user.id}"))
    db.commit()

    steps: list[dict[str, Any]] = []
    plan_steps = plan.get("steps") or []
    for index, step in enumerate(plan_steps, start=1):
        agent_id = step.get("agent", "orchestrator")
        step_name = step.get("name", agent_id)
        # These are the only mission actions this backend currently verifies directly.
        if agent_id == "jobs":
            from ..routers.jobs import research_public_jobs
            query = re.sub(
                r"^(?:tafuta|nitafutie|tafutia|find(?: me)?|search for|search|research|job research)\b",
                "", request.strip(), flags=re.IGNORECASE,
            ).strip(" :,-")
            query = re.sub(
                r"^(?:ajira|kazi|jobs?)(?:\s+(?:za\s+)?remote)?(?:\s+(?:za|for|in))?\s*",
                "", query, flags=re.IGNORECASE,
            ).strip() or "remote jobs"
            try:
                result = await research_public_jobs(query, limit=15)
                result_status = str(result.get("status", "FAILED")).upper()
                successful = result_status in {"COMPLETED", "NO_RESULTS"}
                count = int(result.get("count") or len(result.get("results") or []))
                evidence = {
                    "message": f"Utafutaji umekamilika; matokeo: {count}. Hakuna ombi la kazi lililotumwa.",
                    "query": query, "count": count, "sources": result.get("sources", []),
                    "source_warnings": result.get("source_warnings", []),
                    "results": (result.get("results") or [])[:5],
                    "note": result.get("note", "Thibitisha taarifa kwa tovuti ya mwajiri."),
                }
                steps.append({"step": index, "agent": agent_id, "name": step_name,
                    "tool": "public_job_feeds", "status": "COMPLETED" if successful else "FAILED",
                    "verified": successful, "evidence": evidence})
            except Exception as exc:
                steps.append({"step": index, "agent": agent_id, "name": step_name, "tool": "public_job_feeds",
                    "status": "FAILED", "verified": False,
                    "evidence": {"message": f"Utafutaji umeshindwa: {type(exc).__name__}.", "query": query}})
            continue

        if agent_id == "orchestrator" and "system_telemetry" in step.get("tools", []):
            steps.append({"step": index, "agent": agent_id, "name": step_name,
                "tool": "system_telemetry", "status": "COMPLETED", "verified": True,
                "evidence": system_status(user)})
            continue

        route = route_command(request)
        tool_id = route.get("tool")
        if agent_id in {"browser", "research"} and "browser_hands" in step.get("tools", []):
            handoff = build_browser_handoff(request)
            if handoff:
                steps.append({"step": index, "agent": agent_id, "name": step_name, "tool": "browser_hands",
                    "status": "WAITING_FOR_HAND", "verified": False, "handoff": handoff,
                    "evidence": {"message": "Handoff imetayarishwa kwa extension; hatua ya browser yenyewe haijathibitishwa."}})
                continue
        if tool_id == "searxng" and "searxng" in step.get("tools", []):
            search_tool = next((x for x in registry_summary()["tools"] if x["id"] == "searxng"), None)
            status = "NOT_CONNECTED" if not search_tool or search_tool["status"] != "CONNECTED" else "WAITING_FOR_HAND"
            message = "SearXNG haijaunganishwa." if status == "NOT_CONNECTED" else "Tumia search dispatch yenye ruhusa kutekeleza utafutaji."
            steps.append({"step": index, "agent": agent_id, "name": step_name, "tool": tool_id,
                "status": status, "verified": False, "evidence": {"message": message}})
            continue
        steps.append({"step": index, "agent": agent_id, "name": step_name,
            "tool": (step.get("tools") or [None])[0], "status": "WAITING_FOR_HAND", "verified": False,
            "evidence": {"message": "Hakuna connected execution hand iliyothibitisha kitendo hiki."}})

    # Persist a durable row per planned step. A client-supplied or unverified handoff
    # never receives state=verified.
    for index, result_step in enumerate(steps, start=1):
        status = str(result_step.get("status") or "WAITING").upper()
        evidence_obj = result_step.get("evidence")
        evidence = json.dumps(evidence_obj, ensure_ascii=False, default=str) if evidence_obj else None
        verified = status == "COMPLETED" and result_step.get("verified") is True and bool(evidence and evidence.strip())
        step_state = "verified" if verified else "failed" if status == "FAILED" else "pending"
        db.add(TaskStep(task_id=mission.id, position=index,
            title=str(result_step.get("name") or result_step.get("agent") or f"Hatua {index}")[:255],
            state=step_state, evidence=evidence,
            verified_at=datetime.now(timezone.utc).replace(tzinfo=None) if verified else None))

    db.flush()
    persisted_steps = db.query(TaskStep).filter(TaskStep.task_id == mission.id).all()
    verified_total = sum(
        str(row.state).lower() == "verified" and bool(str(row.evidence or "").strip())
        for row in persisted_steps
    )
    all_verified = bool(persisted_steps) and verified_total == len(persisted_steps)
    failed = any(str(row.get("status", "")).upper() == "FAILED" for row in steps)
    waiting = any(str(row.get("status", "")).upper() in {
        "WAITING", "WAITING_FOR_HAND", "WAITING_FOR_VERIFICATION", "WAITING_APPROVAL", "NOT_CONNECTED"
    } for row in steps)
    mission.status = "COMPLETED" if all_verified else "WAITING" if waiting else "FAILED" if failed else "WAITING_FOR_VERIFICATION"
    mission.progress = int(verified_total / len(persisted_steps) * 100) if persisted_steps else 0
    mission.result = json.dumps({"steps": steps, "verified_steps": verified_total, "total_steps": len(persisted_steps)},
        ensure_ascii=False, default=str)
    mission.error = next((str(row.get("evidence", {}).get("message", "")) for row in steps
        if str(row.get("status", "")).upper() == "FAILED" and isinstance(row.get("evidence"), dict)), None)
    db.add(ActivityLog(user_id=user.id,
        action="MISSION_COMPLETED" if all_verified else "MISSION_FAILED" if mission.status == "FAILED" else "MISSION_WAITING",
        details=f"task_id={mission.id}; status={mission.status}; verified={verified_total}/{len(persisted_steps)}"))
    db.commit()
    db.refresh(mission)
    return {
        "status": mission.status, "mission": _task_payload(mission), "plan": plan, "steps": steps,
        "next_action": "Hatua zote zimethibitishwa kwa ushahidi." if all_verified
            else "Kagua ushahidi wa hatua iliyoshindwa kisha rekebisha sababu." if mission.status == "FAILED"
            else "Unganisha execution hand iliyoombwa; mission haijakamilika mpaka hatua zote ziwe verified.",
    }
