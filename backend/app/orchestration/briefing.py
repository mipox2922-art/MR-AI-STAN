from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session
from ..models import ActivityLog, Setting, SystemErrorLog, Task, TaskStep
from ..routers.system import system_status
from ..tools.registry import registry_summary
from ..agents.registry import AGENTS

ACTIVE_TASK_STATES = {"IN_PROGRESS", "RUNNING", "WORKING", "STARTED"}
WAITING_TASK_STATES = {"PENDING", "WAITING", "BLOCKED", "WAITING_APPROVAL", "WAITING_FOR_HAND", "WAITING_FOR_VERIFICATION", "WAITING_FOR_PROFILE", "READY_FOR_REVIEW"}
FAILED_TASK_STATES = {"FAILED", "ERROR"}

def _utc_iso(value: datetime | None) -> str | None:
    if value is None: return None
    if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def _step_verified(step: TaskStep) -> bool:
    return str(step.state or "").lower() == "verified" and bool(str(step.evidence or "").strip())

def _agent_runtime_status(agent_id: str, user: Any, db: Session, tool_status: dict[str, str]) -> str:
    """Report execution capability, not a decorative online badge."""
    if agent_id in {"orchestrator", "jobs", "memory"}:
        # These paths execute through backend code and persist their results.
        return "READY"
    if agent_id == "gmail":
        try:
            from ..connectors.gmail import connection_status
            state = connection_status(db, user.id)
            if state.get("connected") is True:
                return "CONNECTED"
            return "NOT_CONNECTED" if state.get("configured") else "NOT_CONFIGURED"
        except Exception:
            return "NOT_CONNECTED"
    if agent_id == "research":
        return "CONFIGURED" if tool_status.get("searxng") == "CONNECTED" else "NOT_CONNECTED"
    if agent_id == "scheduler":
        return "AVAILABLE"
    # Registered does not imply a live execution connection.
    if agent_id in {"browser", "coding", "creative", "device", "security"}:
        return "WAITING_FOR_HAND"
    return "NOT_CONFIGURED"


def _safe_task(db: Session, task: Task) -> dict[str, Any]:
    steps = db.query(TaskStep).filter(TaskStep.task_id == task.id).order_by(TaskStep.position.asc()).all()
    verified = sum(_step_verified(step) for step in steps)
    progress = int(verified / len(steps) * 100) if steps else 0
    status = str(task.status or "PENDING").upper()
    if status in {"COMPLETED", "DONE"} and (not steps or verified != len(steps)): status = "WAITING_FOR_VERIFICATION"
    return {
        "id": task.id, "title": task.title, "description": task.description,
        "source": task.source or "unknown", "requested_by": task.requested_by or "Haijathibitishwa",
        "agent": task.agent or "Haijathibitishwa", "status": status, "priority": task.priority,
        "progress": 100 if status in {"COMPLETED", "DONE"} and steps and verified == len(steps) else progress,
        "verified_steps": verified, "step_count": len(steps),
        "steps": [{"id": s.id, "title": s.title, "state": s.state,
                   "has_evidence": bool(str(s.evidence or "").strip()),
                   "evidence_summary": str(s.evidence).strip()[:300] if _step_verified(s) else None,
                   "verified_at": _utc_iso(s.verified_at)} for s in steps],
        "error": task.error, "result": task.result, "created_at": _utc_iso(task.created_at),
        "updated_at": _utc_iso(task.updated_at), "approved_by": task.approved_by, "approved_at": _utc_iso(task.approved_at),
        "next_action": (
            "Inasubiri idhini ya Boss Ferisi." if status == "WAITING_APPROVAL"
            else (task.error or "Kagua sababu na ushahidi wa hitilafu.") if status in FAILED_TASK_STATES
            else "Kagua/ongeza ushahidi wa hatua zilizobaki." if status == "WAITING_FOR_VERIFICATION"
            else "Endelea baada ya muunganisho wa zana inayohitajika." if status == "WAITING_FOR_HAND"
            else "Endelea na hatua inayofuata; hakuna hatua inayohesabiwa hadi iwe na ushahidi." if status in WAITING_TASK_STATES | ACTIVE_TASK_STATES
            else "Hatua zote zimethibitishwa kwa ushahidi." if status in {"COMPLETED", "DONE"}
            else "Haijathibitishwa."
        ),
    }

def build_executive_briefing(user: Any, db: Session) -> dict[str, Any]:
    """Build a truthful report from persisted tasks, evidence, logs and registered tool data."""
    now = datetime.now(timezone.utc)
    tasks = db.query(Task).filter(Task.user_id == user.id).order_by(Task.id.desc()).limit(200).all()
    activities = db.query(ActivityLog).filter(ActivityLog.user_id == user.id).order_by(ActivityLog.id.desc()).limit(15).all()
    error_rows = db.query(SystemErrorLog).filter(SystemErrorLog.user_id == user.id).order_by(SystemErrorLog.id.desc()).limit(15).all()
    task_rows = [_safe_task(db, task) for task in tasks]
    counts = Counter(str(row["status"] or "PENDING").upper() for row in task_rows)
    assignments: dict[str, list[dict[str, Any]]] = {}
    for row in task_rows:
        agent_id = str(row.get("agent") or "").strip().lower()
        if agent_id != "haijathibitishwa": assignments.setdefault(agent_id, []).append(row)
    tool_snapshot = registry_summary()
    tool_status = {
        str(item.get("id") or ""): str(item.get("status") or "")
        for item in tool_snapshot.get("tools", [])
    }
    fleet = []
    for definition in AGENTS:
        rows = assignments.get(definition.id, [])
        runtime_state = _agent_runtime_status(definition.id, user, db, tool_status)
        active_task = next((r for r in rows if r["status"] in ACTIVE_TASK_STATES), None)
        waiting_task = next((r for r in rows if r["status"] in WAITING_TASK_STATES), None)
        failed_task = next((r for r in rows if r["status"] in FAILED_TASK_STATES), None)
        current = active_task or waiting_task or failed_task
        if active_task:
            state = "WORKING"
        elif waiting_task:
            state = "WAITING"
        elif failed_task:
            state = "FAILED"
        else:
            state = runtime_state
        done = [r for r in rows if r["status"] in {"COMPLETED", "DONE"}]
        fleet.append({
            "id": definition.id, "name": definition.name, "description": definition.description,
            "status": state, "runtime_status": runtime_state,
            "risk": definition.risk, "tools": list(definition.tools),
            "capability_count": len(definition.tools),
            "current_task": ({"id": current["id"], "title": current["title"], "status": current["status"],
                "progress": current["progress"], "waiting_for": current["next_action"] if waiting_task else None,
                "error": current["error"]} if current else None),
            "completed_tasks": [{"id": r["id"], "title": r["title"], "verified_steps": r["verified_steps"],
                "step_count": r["step_count"], "updated_at": r["updated_at"]} for r in done[:3]],
        })
    recent_activity = [{"id": x.id, "action": x.action, "details": x.details, "created_at": _utc_iso(x.created_at)} for x in activities]
    errors = [{"id": x.id, "component": x.component, "code": x.code, "message": x.message_safe, "created_at": _utc_iso(x.created_at)} for x in error_rows]
    system = system_status(user)
    tools = registry_summary()
    completed = sum(r["status"] in {"COMPLETED", "DONE"} for r in task_rows)
    active = sum(r["status"] in ACTIVE_TASK_STATES for r in task_rows)
    waiting = sum(r["status"] in WAITING_TASK_STATES for r in task_rows)
    failed = sum(r["status"] in FAILED_TASK_STATES for r in task_rows)
    approvals = [r for r in task_rows if r["status"] == "WAITING_APPROVAL"]
    blockers = []
    if tools.get("not_connected", 0) or tools.get("optional", 0): blockers.append({"type": "TOOL_CONNECTIVITY", "message": "Baadhi ya zana hazijaunganishwa au hazijasanidiwa."})
    if failed: blockers.append({"type": "TASK_FAILURES", "message": f"{failed} kazi zimeshindwa; sababu ziko kwenye rekodi za kazi."})
    if approvals: blockers.append({"type": "BOSS_APPROVAL", "message": f"Kazi {len(approvals)} zinasubiri idhini ya Boss Ferisi."})
    if errors: blockers.append({"type": "RECORDED_ERRORS", "message": f"Hitilafu {len(errors)} za karibuni zimehifadhiwa kwenye audit trail."})
    storage = (system.get("telemetry") or {}).get("storage_percent")
    if isinstance(storage, (int, float)) and storage >= 80: blockers.append({"type": "STORAGE_THRESHOLD", "message": f"Storage iko {storage:.1f}%; imevuka kizingiti cha tahadhari cha 80%."})
    next_action = (
        "Boss Ferisi aidhinishe kazi inayosubiri idhini." if approvals
        else "Kagua kazi zilizoshindwa na sababu zilizo kwenye audit trail." if failed
        else "Kagua ushahidi wa hatua zilizobaki; kazi haiwezi kukamilika bila ushahidi." if any(r["status"] == "WAITING_FOR_VERIFICATION" for r in task_rows)
        else "Unganisha zana zilizo NOT_CONNECTED kabla ya hatua za nje." if tools.get("not_connected", 0)
        else "Hakuna kazi kwenye database; hakuna kazi inayoendelea iliyothibitishwa." if not task_rows
        else "Kagua ripoti ya kazi na chagua hatua inayofuata."
    )

    job_rows = [
        row for row in task_rows
        if str(row.get("agent") or "").casefold() == "jobs"
        and str(row.get("source") or "").casefold() == "autopilot"
    ]
    job_packets: list[dict[str, Any]] = []
    for row in job_rows:
        try:
            packet = json.loads(row.get("result") or "{}")
        except (TypeError, ValueError):
            packet = {}
        if isinstance(packet, dict) and packet.get("workflow") == "JOB_APPLICATION":
            job_packets.append(packet)
    config_row = (
        db.query(Setting)
        .filter(Setting.user_id == user.id, Setting.key == "job_autopilot_config")
        .order_by(Setting.id.desc())
        .first()
    )
    try:
        job_config = json.loads(config_row.value or "{}") if config_row else {"enabled": True}
    except (TypeError, ValueError):
        job_config = {"enabled": True}
    job_autopilot = {
        "enabled": bool(job_config.get("enabled", True)),
        "last_run_at": job_config.get("last_run_at"),
        "jobs_found": len(job_packets),
        "drafts_ready": sum(1 for row in job_rows if row["status"] == "READY_FOR_REVIEW"),
        "waiting_for_profile": sum(1 for row in job_rows if row["status"] == "WAITING_FOR_PROFILE"),
        "applications_submitted_automatically": sum(
            1 for packet in job_packets
            if str((packet.get("submission") or {}).get("status") or "").upper() == "SUBMITTED"
            and (packet.get("submission") or {}).get("verified") is True
        ),
        "auto_submit_available": False,
        "submission_blocker": "Application form/email submission is not connected to a verified execution hand.",
    }
    return {
        "status": "COMPLETED", "generated_at": now.isoformat().replace("+00:00", "Z"),
        "timezone": "Africa/Dar_es_Salaam", "system": system,
        "agents": {"total": len(fleet), "working": sum(x["status"] == "WORKING" for x in fleet),
            "waiting": sum(x["status"] in {"WAITING", "WAITING_FOR_HAND", "NOT_CONNECTED", "NOT_CONFIGURED", "FAILED"} for x in fleet),
            "fleet": fleet},
        "tasks": {"total": len(task_rows), "completed": completed, "working": active, "waiting": waiting,
            "failed": failed, "counts": dict(counts), "items": task_rows, "pending_approval": approvals},
        "recent_activity": recent_activity, "errors": errors, "tools": tools,
        "job_autopilot": job_autopilot,
        "financial": {"status": "NOT_CONNECTED", "message": "Hakuna muunganisho wa fedha uliothibitishwa."},
        "social": {"status": "NOT_CONNECTED", "message": "Hakuna muunganisho wa uchapishaji wa mitandao ya kijamii uliothibitishwa."},
        "discoveries": [], "blockers": blockers, "next_action": next_action,
        "truth_boundary": [
            "Hatua ni verified ikiwa state ni verified na evidence si tupu.",
            "Kazi isiyo na hatua zenye ushahidi haihesabiwi completed.",
            "Idhini ya Boss haimaanishi kazi imeanza au kukamilika.",
            "Wakala huonyeshwa WORKING tu ikiwa task record inaonyesha hali inayotumika.",
            "Backend hutuma muda UTC; UI huubadilisha kuwa Africa/Dar_es_Salaam.",
        ],
    }
