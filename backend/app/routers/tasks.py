from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..audit import redact_sensitive_text
from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog, ApprovalRequest, Task, TaskStep
from ..realtime import manager
from ..schemas import TaskCreate, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["Tasks"])

def _utc_iso(value: datetime | None) -> str | None:
    if value is None: return None
    if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def step_is_verified(step: TaskStep) -> bool:
    return str(step.state or "").lower() == "verified" and bool(str(step.evidence or "").strip())

def progress_of(steps: list[TaskStep]) -> int:
    return int(sum(step_is_verified(step) for step in steps) / len(steps) * 100) if steps else 0

def can_mark_done(steps: list[TaskStep]) -> bool:
    return bool(steps) and all(step_is_verified(step) for step in steps)

def _steps_for(db: Session, task_id: int) -> list[TaskStep]:
    return db.query(TaskStep).filter(TaskStep.task_id == task_id).order_by(TaskStep.position.asc()).all()

def _next_action(status: str, task: Task, steps: list[TaskStep]) -> str:
    if status == "WAITING_APPROVAL": return "Inasubiri idhini ya Boss Ferisi."
    if status == "PENDING" and task.source == "orchestrator" and task.approved_by:
        return "Boss ametoa idhini; bofya ANZA MISSION ili kutekeleza hatua zilizoidhinishwa."
    if status == "PENDING" and task.source == "agent" and task.approved_by:
        return "Idhini imehifadhiwa, lakini executor ya wakala haijaunganishwa; kazi haijatekelezwa."
    if status == "WAITING_FOR_HAND": return "Inahitaji Browser/Device/Gmail hand iliyounganishwa."
    if status == "WAITING_FOR_VERIFICATION": return "Kagua au ongeza ushahidi wa hatua zilizobaki."
    if status in {"FAILED", "ERROR"}: return task.error or "Kazi imeshindwa; sababu zaidi haijathibitishwa."
    if status in {"COMPLETED", "DONE"} and can_mark_done(steps): return "Hatua zote zimethibitishwa kwa ushahidi."
    if status in {"PENDING", "WAITING", "IN_PROGRESS", "RUNNING"}: return "Endelea na hatua inayofuata, kisha hifadhi ushahidi."
    return "Haijathibitishwa."

def task_payload(db: Session, task: Task) -> dict[str, Any]:
    steps = _steps_for(db, task.id)
    verified = sum(step_is_verified(step) for step in steps)
    status = str(task.status or "PENDING").upper()
    if status in {"COMPLETED", "DONE"} and not can_mark_done(steps): status = "WAITING_FOR_VERIFICATION"
    safe_steps = [{
        "id": step.id, "position": step.position, "title": step.title, "state": step.state,
        "has_evidence": bool(str(step.evidence or "").strip()),
        "evidence": redact_sensitive_text(step.evidence, 500) if step.evidence else None,
        "verified_at": _utc_iso(step.verified_at),
    } for step in steps]
    return {
        "id": task.id, "user_id": task.user_id, "title": task.title, "description": task.description,
        "status": status, "priority": task.priority, "deadline": _utc_iso(task.deadline),
        "agent": task.agent or "Haijathibitishwa", "source": task.source or "unknown",
        "requested_by": task.requested_by or "Haijathibitishwa", "approved_by": task.approved_by,
        "approved_at": _utc_iso(task.approved_at),
        "progress": 100 if status in {"COMPLETED", "DONE"} and can_mark_done(steps) else progress_of(steps),
        "verified_steps": verified, "step_count": len(steps), "steps": safe_steps, "result": task.result,
        "error": redact_sensitive_text(task.error, 500) if task.error else None,
        "created_at": _utc_iso(task.created_at), "updated_at": _utc_iso(task.updated_at),
        "next_action": _next_action(status, task, steps),
    }

@router.post("")
async def create_task(data: TaskCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    task = Task(user_id=current_user.id, title=data.title.strip(), description=data.description,
        priority=data.priority, deadline=data.deadline, agent=data.agent, status="PENDING",
        source="boss", requested_by=str(getattr(current_user, "username", None) or "Boss Ferisi"), progress=0)
    db.add(task); db.flush()
    db.add(ActivityLog(user_id=current_user.id, action="TASK_CREATED", details=f"task_id={task.id}; source=boss"))
    db.commit(); db.refresh(task)
    await manager.broadcast("TASK_CREATED", {"task_id": task.id}, user_id=current_user.id)
    return task_payload(db, task)

@router.get("")
def list_tasks(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Task).filter(Task.user_id == current_user.id).order_by(Task.id.desc()).limit(200).all()
    return [task_payload(db, task) for task in rows]

@router.post("/{task_id}/approve")
async def approve_task(task_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task: raise HTTPException(404, "Task not found")
    if task.status != "WAITING_APPROVAL": raise HTTPException(409, "Task is not waiting for approval")
    if (task.source or "").lower() not in {"orchestrator", "agent"}:
        raise HTTPException(403, "Only agent/orchestrator proposals can use this approval path")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task.approved_by = current_user.id
    task.approved_at = now
    task.status = "PENDING" if task.agent == "orchestrator" else "WAITING_FOR_HAND"
    task.error = None if task.status == "PENDING" else "Idhini imerekodiwa; agent hii haina executor iliyothibitishwa ya kuanza hatua hii moja kwa moja."
    for approval in db.query(ApprovalRequest).filter(ApprovalRequest.user_id == current_user.id, ApprovalRequest.status == "PENDING").all():
        try: payload = json.loads(approval.payload or "{}")
        except (TypeError, ValueError): continue
        if payload.get("task_id") == task.id:
            approval.status = "APPROVED"; approval.resolved_at = now
    db.add(ActivityLog(user_id=current_user.id, action="TASK_APPROVED", details=f"task_id={task.id}; source={task.source}; decision=APPROVED"))
    db.commit(); db.refresh(task)
    await manager.broadcast("TASK_APPROVED", {"task_id": task.id, "status": task.status, "approved_by": current_user.id}, user_id=current_user.id)
    return {**task_payload(db, task), "message": "Idhini imehifadhiwa. Kazi haijathibitishwa kuwa imeanza au kukamilika."}

@router.post("/{task_id}/steps")
async def add_task_step(task_id: int, payload: dict, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task: raise HTTPException(404, "Task not found")
    if task.status in {"COMPLETED", "DONE"}: raise HTTPException(409, "Reopen the task before adding steps")
    if task.source in {"agent", "orchestrator"} and not task.approved_by:
        raise HTTPException(403, "Boss approval is required before editing execution steps")
    title = str(payload.get("title") or "").strip()
    if not title: raise HTTPException(400, "Step title is required")
    position = (db.query(TaskStep).filter(TaskStep.task_id == task.id).count() or 0) + 1
    db.add(TaskStep(task_id=task.id, position=position, title=title[:255], state="pending")); db.flush()
    task.progress = progress_of(_steps_for(db, task.id))
    db.add(ActivityLog(user_id=current_user.id, action="TASK_STEP_ADDED", details=f"task_id={task.id}; step_position={position}"))
    db.commit(); db.refresh(task)
    return task_payload(db, task)

@router.patch("/{task_id}/steps/{step_id}")
async def update_task_step(task_id: int, step_id: int, payload: dict, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task: raise HTTPException(404, "Task not found")
    step = db.query(TaskStep).filter(TaskStep.id == step_id, TaskStep.task_id == task.id).first()
    if not step: raise HTTPException(404, "Task step not found")
    if task.source in {"agent", "orchestrator"} and not task.approved_by:
        raise HTTPException(403, "Boss approval is required before editing execution steps")
    new_state = str(payload.get("state", step.state)).strip().lower()
    if new_state not in {"pending", "running", "verified", "failed"}:
        raise HTTPException(400, "state must be pending, running, verified, or failed")
    evidence_value = payload.get("evidence", step.evidence)
    evidence = redact_sensitive_text(evidence_value, 12000) if evidence_value is not None else None
    if new_state == "verified" and not str(evidence or "").strip():
        raise HTTPException(400, "A step needs non-empty evidence before it can be verified")
    step.state = new_state; step.evidence = evidence
    step.verified_at = datetime.now(timezone.utc).replace(tzinfo=None) if new_state == "verified" else None
    db.flush(); steps = _steps_for(db, task.id); task.progress = progress_of(steps)
    failed_steps = [item for item in steps if item.state == "failed"]
    if failed_steps:
        task.status = "FAILED"; task.error = f"Step failed: {failed_steps[0].title}"
    elif can_mark_done(steps):
        task.status = "COMPLETED"; task.progress = 100; task.error = None
    elif task.status in {"COMPLETED", "DONE"}:
        task.status = "WAITING_FOR_VERIFICATION"; task.progress = progress_of(steps)
    db.add(ActivityLog(user_id=current_user.id, action="TASK_STEP_UPDATED",
        details=f"task_id={task.id}; step_id={step.id}; state={step.state}; has_evidence={bool(str(step.evidence or '').strip())}"))
    db.commit(); db.refresh(task)
    verified_count = sum(step_is_verified(item) for item in _steps_for(db, task.id))
    await manager.broadcast("TASK_PROGRESS", {"task_id": task.id, "status": task.status, "progress": task.progress, "verified_steps": verified_count}, user_id=current_user.id)
    return task_payload(db, task)

@router.patch("/{task_id}")
async def update_task(task_id: int, data: TaskUpdate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task: raise HTTPException(404, "Task not found")
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates and task.source in {"orchestrator", "agent"} and not task.approved_by and updates["status"] != "WAITING_APPROVAL":
        raise HTTPException(403, "An agent-proposed task must be approved by Boss Ferisi first")
    for key, value in updates.items(): setattr(task, key, value)
    steps = _steps_for(db, task.id); task.progress = progress_of(steps)
    if task.status in {"COMPLETED", "DONE"} and not can_mark_done(steps): task.status = "WAITING_FOR_VERIFICATION"
    db.add(ActivityLog(user_id=current_user.id, action="TASK_UPDATED", details=f"task_id={task.id}; status={task.status}"))
    db.commit(); db.refresh(task)
    event = "TASK_FAILED" if task.status == "FAILED" else "TASK_WAITING" if task.status in {"WAITING", "WAITING_FOR_HAND", "WAITING_APPROVAL", "WAITING_FOR_VERIFICATION"} else "TASK_PROGRESS"
    await manager.broadcast(event, {"task_id": task.id, "status": task.status, "progress": task.progress, "error": bool(task.error)}, user_id=current_user.id)
    return task_payload(db, task)
