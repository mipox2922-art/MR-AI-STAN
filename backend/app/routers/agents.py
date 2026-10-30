import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog, ApprovalRequest, Setting, Task, TaskStep
from ..routers.system import system_status
from ..agents.registry import AGENTS
from ..orchestration.planner import build_plan
from ..orchestration.briefing import build_executive_briefing
from ..orchestration.executor import execute_mission

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("")
def list_agents(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    briefing = build_executive_briefing(current_user, db)
    runtime_by_id = {
        item["id"]: item
        for item in (briefing.get("agents") or {}).get("fleet", [])
    }
    return [
        {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "capabilities": list(agent.capabilities),
            "tools": list(agent.tools),
            "capability_count": len(agent.tools),
            "risk": agent.risk,
            "status": runtime_by_id.get(agent.id, {}).get("status", "NOT_CONFIGURED"),
            "runtime_status": runtime_by_id.get(agent.id, {}).get("runtime_status", "NOT_CONFIGURED"),
            "current_task": runtime_by_id.get(agent.id, {}).get("current_task"),
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


BROWSER_COMMAND_TTL_SECONDS = 180
BROWSER_RESULT_MAX_BYTES = 30000
BROWSER_HEARTBEAT_KEY = "browser_hands.last_seen"
BROWSER_HEARTBEAT_TTL_SECONDS = 90


def _record_browser_heartbeat(db: Session, user_id: int) -> str:
    """Persist authenticated extension polling as a per-owner live heartbeat."""
    now = datetime.now(timezone.utc)
    row = db.query(Setting).filter(
        Setting.user_id == user_id,
        Setting.key == BROWSER_HEARTBEAT_KEY,
    ).order_by(Setting.id.desc()).first()
    if row is not None:
        try:
            previous = datetime.fromisoformat(str(row.value or "").replace("Z", "+00:00"))
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            if (now - previous).total_seconds() < 20:
                return previous.isoformat()
        except (TypeError, ValueError):
            pass
        row.value = now.isoformat()
    else:
        db.add(Setting(user_id=user_id, key=BROWSER_HEARTBEAT_KEY, value=now.isoformat()))
    db.commit()
    return now.isoformat()


def _browser_heartbeat_status(db: Session, user_id: int) -> dict:
    row = db.query(Setting).filter(
        Setting.user_id == user_id,
        Setting.key == BROWSER_HEARTBEAT_KEY,
    ).order_by(Setting.id.desc()).first()
    if row is None or not row.value:
        return {"status": "WAITING_FOR_HAND", "connected": False, "last_seen": None}
    try:
        seen = datetime.fromisoformat(str(row.value).replace("Z", "+00:00"))
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return {"status": "WAITING_FOR_HAND", "connected": False, "last_seen": None}
    age = max(0.0, (datetime.now(timezone.utc) - seen).total_seconds())
    connected = age <= BROWSER_HEARTBEAT_TTL_SECONDS
    return {
        "status": "CONNECTED" if connected else "WAITING_FOR_HAND",
        "connected": connected,
        "last_seen": seen.isoformat(),
        "age_seconds": int(age),
    }


def _parse_browser_command(task: Task) -> dict:
    try:
        data = json.loads(task.description or "{}")
    except (TypeError, ValueError) as exc:
        raise HTTPException(409, "Browser command record is invalid.") from exc
    if not isinstance(data, dict):
        raise HTTPException(409, "Browser command record is invalid.")
    action = str(data.get("action") or "")
    if action not in {"GET_PAGE_DATA", "NAVIGATE", "SCROLL", "TYPE", "CLICK", "DRAG"}:
        raise HTTPException(409, "Browser command action is unsupported.")
    if not isinstance(data.get("payload") or {}, dict):
        raise HTTPException(409, "Browser command payload is invalid.")
    return data


def _browser_result_is_verified(command: dict, result: dict) -> bool:
    action = command.get("action")
    if result.get("action") != action or result.get("verified") is not True:
        return False

    target_url = result.get("targetUrl")
    target_host = str(result.get("targetHost") or "").casefold()
    parsed_target = urlparse(str(target_url or ""))
    if parsed_target.scheme not in {"http", "https"} or not parsed_target.hostname:
        return False
    if parsed_target.hostname.casefold() != target_host:
        return False

    if action == "GET_PAGE_DATA":
        page = result.get("page")
        if not isinstance(page, dict):
            return False
        parsed_page = urlparse(str(page.get("url") or ""))
        return bool(
            parsed_page.scheme in {"http", "https"}
            and parsed_page.hostname
            and parsed_page.hostname.casefold() == target_host
            and isinstance(page.get("title"), str)
            and isinstance(page.get("text"), str)
            and len(page.get("text", "")) <= 20000
        )

    if action == "SCROLL":
        before_y, after_y = result.get("beforeY"), result.get("afterY")
        return (
            isinstance(before_y, (int, float))
            and isinstance(after_y, (int, float))
            and abs(after_y - before_y) > 0
        )

    if action == "TYPE":
        element = result.get("element")
        expected_value = (command.get("payload") or {}).get("value")
        if not isinstance(element, dict) or not isinstance(expected_value, str):
            return False
        tag = str(element.get("tag") or "").casefold()
        input_type = str(element.get("type") or "").casefold()
        autocomplete = str(element.get("autocomplete") or "").casefold()
        sensitive = (
            input_type == "password"
            or autocomplete in {"one-time-code", "cc-number", "cc-csc", "cc-exp"}
            or any(term in " ".join([
                str(element.get("id") or ""),
                str(element.get("name") or ""),
                str(element.get("ariaLabel") or ""),
                str(element.get("placeholder") or ""),
                autocomplete,
            ]).casefold() for term in (
                "password", "passcode", "otp", "credit-card", "card-number",
                "cvv", "cvc", "security-code", "bank-pin",
            ))
        )
        input_writable = tag == "input" and input_type in {"text", "search", "email", "tel", "url", "number"}
        textarea_writable = tag == "textarea"
        content_editable = element.get("contentEditable") is True
        expected_length = len(expected_value.encode("utf-16-le")) // 2
        return bool(
            (input_writable or textarea_writable or content_editable)
            and not sensitive
            and result.get("valueLength") == expected_length
        )

    return False


def _redacted_browser_output(value: dict) -> dict:
    # Do not persist arbitrary oversized browser responses or credential-like
    # fields. Page text remains available to the owner but is strictly bounded.
    cleaned = dict(value)
    page = cleaned.get("page")
    if isinstance(page, dict):
        cleaned["page"] = {
            "title": str(page.get("title") or "")[:500],
            "url": str(page.get("url") or "")[:2000],
            "text": str(page.get("text") or "")[:12000],
        }
    return cleaned


def _reconcile_browser_command(
    db: Session,
    command: Task,
    command_data: dict,
    result: dict | None,
    error: str | None,
    *,
    verified: bool,
    terminal_status: str,
) -> dict:
    now = datetime.utcnow()
    stored_payload = {
        "request_id": command_data["request_id"],
        "mission_id": command_data.get("mission_id"),
        "step_position": command_data.get("step_position"),
        "action": command_data.get("action"),
        "verified": verified,
        "status": terminal_status,
        "result": _redacted_browser_output(result or {}) if result else None,
        "error": error[:1200] if error else None,
    }
    claim_record = {}
    try:
        prior = json.loads(command.result or "{}")
        if isinstance(prior, dict):
            claim_hash = str(prior.get("claim_token_hash") or "")
            if claim_hash:
                claim_record = {"claim_token_hash": claim_hash}
    except (TypeError, ValueError):
        pass
    stored_payload.update(claim_record)
    command.result = json.dumps(stored_payload, ensure_ascii=False, default=str)
    command.error = (error[:1200] if error else None)
    command.updated_at = now
    command.progress = 100 if verified else 0
    command.status = terminal_status

    # A completed receipt task must itself carry verified TaskStep evidence.
    # Otherwise GET /tasks correctly downgrades COMPLETED records with zero steps
    # to WAITING_FOR_VERIFICATION, even though the parent mission was verified.
    child_step = db.query(TaskStep).filter(
        TaskStep.task_id == command.id,
        TaskStep.position == 1,
    ).first()
    if child_step is None:
        child_step = TaskStep(
            task_id=command.id,
            position=1,
            title="Execute browser action and verify returned state",
        )
        db.add(child_step)
    child_step.title = "Execute browser action and verify returned state"
    child_step.state = (
        "verified" if verified
        else "failed" if terminal_status in {"FAILED", "BLOCKED"}
        else "pending"
    )
    child_step.evidence = json.dumps({
        "task_id": command.id,
        "agent": "browser",
        "tool": "browser_hands",
        "execution_status": terminal_status,
        "verified": verified,
        "action": command_data.get("action"),
        "output": stored_payload["result"],
        "error": stored_payload["error"],
        "request_id": command_data.get("request_id"),
    }, ensure_ascii=False, default=str)
    child_step.verified_at = now if verified else None

    parent_id = command_data.get("mission_id")
    position = command_data.get("step_position")
    parent = None
    step_row = None
    if isinstance(parent_id, int) and isinstance(position, int):
        parent = db.query(Task).filter(
            Task.id == parent_id,
            Task.user_id == command.user_id,
            Task.agent == "orchestrator",
        ).first()
        if parent:
            step_row = db.query(TaskStep).filter(
                TaskStep.task_id == parent.id,
                TaskStep.position == position,
            ).first()

    result_status = (
        "COMPLETED" if terminal_status == "COMPLETED" and verified
        else "FAILED" if terminal_status == "FAILED"
        else "BLOCKED" if terminal_status == "BLOCKED"
        else "WAITING_FOR_VERIFICATION"
    )
    step_item = {
        "step": position,
        "agent": "browser",
        "name": "Browser Agent",
        "tool": "browser_hands",
        "command_task_id": command.id,
        "request_id": command_data["request_id"],
        "status": result_status,
        "verified": verified,
        "evidence": {
            "command_task_id": command.id,
            "action": command_data.get("action"),
            "output": stored_payload["result"],
            "error": error[:1200] if error else None,
            "verified": verified,
        },
    }

    if step_row:
        step_row.state = "verified" if result_status == "COMPLETED" else "failed" if result_status == "FAILED" else "pending"
        step_row.evidence = json.dumps({
            "task_id": parent.id,
            "agent": "browser",
            "tool": "browser_hands",
            "execution_status": result_status,
            "verified": verified,
            "output": step_item["evidence"],
            "step_result": step_item,
        }, ensure_ascii=False, default=str)
        step_row.verified_at = now if verified else None

    if parent:
        try:
            parent_result = json.loads(parent.result or "{}")
        except (TypeError, ValueError):
            parent_result = {}
        if not isinstance(parent_result, dict):
            parent_result = {}
        result_steps = parent_result.get("steps")
        if not isinstance(result_steps, list):
            result_steps = []
        while len(result_steps) < (position or 1):
            result_steps.append({})
        result_steps[position - 1] = step_item
        parent_result["steps"] = result_steps

        from .tasks import can_mark_done, progress_of
        parent_steps = db.query(TaskStep).filter(TaskStep.task_id == parent.id).order_by(TaskStep.position.asc()).all()
        parent.progress = progress_of(parent_steps)
        if can_mark_done(parent_steps):
            parent.status = "COMPLETED"
            parent.error = None
            parent.progress = 100
            parent_result["status"] = "COMPLETED"
        elif terminal_status == "FAILED":
            parent.status = "FAILED"
            parent.error = error[:1200] if error else "Browser command failed."
            parent_result["status"] = "FAILED"
        elif terminal_status == "BLOCKED":
            parent.status = "BLOCKED"
            parent.error = error[:1200] if error else "Browser action was blocked by a safety control."
            parent_result["status"] = "BLOCKED"
        else:
            parent.status = "WAITING_FOR_VERIFICATION"
            parent.error = "Browser action returned without sufficient independent evidence to verify the requested state."
            parent_result["status"] = "WAITING_FOR_VERIFICATION"

        parent_result["verified_steps"] = sum(
            str(row.state or "").lower() == "verified" and bool(str(row.evidence or "").strip())
            for row in parent_steps
        )
        parent_result["total_steps"] = len(parent_steps)
        parent.result = json.dumps(parent_result, ensure_ascii=False, default=str)
        parent.updated_at = now

    db.add(ActivityLog(
        user_id=command.user_id,
        action="BROWSER_COMMAND_RESULT",
        details=f"command_id={command.id}; mission_id={parent_id}; status={terminal_status}; verified={verified}",
    ))
    db.commit()
    db.refresh(command)
    if parent:
        db.refresh(parent)
    return {
        "status": terminal_status,
        "verified": verified,
        "command_task_id": command.id,
        "mission": ({
            "id": parent.id,
            "status": parent.status,
            "progress": parent.progress,
            "result": parent.result,
            "error": parent.error,
        } if parent else None),
        "result": stored_payload["result"],
        "error": stored_payload["error"],
    }


@router.get("/browser/status")
def browser_hand_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Expose the last authenticated Chrome-extension heartbeat for this owner."""
    return _browser_heartbeat_status(db, current_user.id)


@router.get("/browser/next")
def claim_browser_command(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Atomically claim one persisted browser command for this authenticated user."""
    _record_browser_heartbeat(db, current_user.id)
    stale_cutoff = datetime.utcnow() - timedelta(seconds=BROWSER_COMMAND_TTL_SECONDS)
    stale_commands = db.query(Task).filter(
        Task.user_id == current_user.id,
        Task.agent == "browser",
        Task.source == "browser_hands",
        Task.status == "RUNNING",
        Task.updated_at < stale_cutoff,
    ).order_by(Task.id.asc()).limit(10).all()
    for stale in stale_commands:
        try:
            command_data = _parse_browser_command(stale)
        except HTTPException:
            stale.status = "FAILED"
            stale.error = "Invalid browser command; it was not retried."
            stale.updated_at = datetime.utcnow()
            db.commit()
            continue
        _reconcile_browser_command(
            db,
            stale,
            command_data,
            None,
            "Browser extension did not return a result before the command timeout. The action was not automatically replayed.",
            verified=False,
            terminal_status="FAILED",
        )

    command = db.query(Task).filter(
        Task.user_id == current_user.id,
        Task.agent == "browser",
        Task.source == "browser_hands",
        Task.status == "QUEUED",
        Task.approved_by == current_user.id,
    ).order_by(Task.id.asc()).first()
    if not command:
        return {"status": "EMPTY", "command": None}

    claim_token = secrets.token_urlsafe(32)
    result = db.execute(
        update(Task)
        .where(
            Task.id == command.id,
            Task.user_id == current_user.id,
            Task.agent == "browser",
            Task.source == "browser_hands",
            Task.status == "QUEUED",
            Task.approved_by == current_user.id,
        )
        .values(status="RUNNING", result=json.dumps({
            "claim_token_hash": hashlib.sha256(claim_token.encode("utf-8")).hexdigest(),
            "claimed_at": datetime.utcnow().isoformat() + "Z",
        }), updated_at=datetime.utcnow())
    )
    db.commit()
    if result.rowcount != 1:
        return {"status": "EMPTY", "command": None}
    db.refresh(command)
    data = _parse_browser_command(command)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="BROWSER_COMMAND_CLAIMED",
        details=f"command_id={command.id}; action={data['action']}",
    ))
    db.commit()
    return {
        "status": "RUNNING",
        "command": {
            "task_id": command.id,
            "request_id": data["request_id"],
            "claim_token": claim_token,
            "mission_id": data.get("mission_id"),
            "step_position": data.get("step_position"),
            "action": data["action"],
            "payload": data.get("payload") or {},
            "boss_approved": data.get("boss_approved") is True,
            "timeout_seconds": 20,
        },
    }


@router.post("/browser/{command_id}/result")
def report_browser_command_result(
    command_id: int,
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    command = db.query(Task).filter(
        Task.id == command_id,
        Task.user_id == current_user.id,
        Task.agent == "browser",
        Task.source == "browser_hands",
    ).first()
    if not command:
        raise HTTPException(404, "Browser command not found.")

    try:
        command_data = json.loads(command.description or "{}")
        prior = json.loads(command.result or "{}")
    except (TypeError, ValueError):
        raise HTTPException(409, "Browser command state is invalid.")
    if not isinstance(command_data, dict) or not isinstance(prior, dict):
        raise HTTPException(409, "Browser command state is invalid.")

    request_id = str(payload.get("request_id") or "")
    claim_token = str(payload.get("claim_token") or "")
    expected_claim_hash = str(prior.get("claim_token_hash") or "")
    supplied_claim_hash = hashlib.sha256(claim_token.encode("utf-8")).hexdigest() if claim_token else ""
    if request_id != command_data.get("request_id") or not expected_claim_hash or not secrets.compare_digest(
        expected_claim_hash, supplied_claim_hash
    ):
        raise HTTPException(409, "Browser result correlation or claim token did not match.")

    # A lost HTTP response may cause a repeat POST. Accept the same completed
    # receipt without executing or applying it a second time.
    if command.status != "RUNNING":
        return {
            "status": "ALREADY_RECORDED",
            "command_task_id": command.id,
            "stored_status": command.status,
        }

    error = str(payload.get("error") or "").strip()[:1200]
    raw_result = payload.get("result")
    if raw_result is not None and not isinstance(raw_result, dict):
        raise HTTPException(422, "Browser result must be an object.")
    raw_result = raw_result or {}
    serialized = json.dumps(raw_result, ensure_ascii=False, default=str)
    if len(serialized.encode("utf-8")) > BROWSER_RESULT_MAX_BYTES:
        raise HTTPException(413, "Browser result exceeds the permitted size.")

    if error:
        blocked = any(marker in error for marker in (
            "BLOCKED_BY_ALLOWLIST", "BLOCKED_SENSITIVE_FIELD", "approvalRequired",
        ))
        return _reconcile_browser_command(
            db, command, command_data, None, error,
            verified=False, terminal_status="BLOCKED" if blocked else "FAILED",
        )

    if raw_result.get("approvalRequired") is True:
        return _reconcile_browser_command(
            db, command, command_data, raw_result,
            str(raw_result.get("reason") or "Browser action needs explicit owner approval."),
            verified=False, terminal_status="BLOCKED",
        )

    if raw_result.get("action") != command_data.get("action"):
        raise HTTPException(422, "Browser result action does not match the queued command.")

    verified = _browser_result_is_verified(command_data, raw_result)
    terminal = "COMPLETED" if verified else "WAITING_FOR_VERIFICATION"
    return _reconcile_browser_command(
        db, command, command_data, raw_result, None,
        verified=verified, terminal_status=terminal,
    )


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
    resumable_states = {"WAITING", "WAITING_FOR_HAND", "WAITING_FOR_VERIFICATION", "FAILED", "BLOCKED"}
    if mission.status in {"RUNNING", "IN_PROGRESS"}:
        updated_at = mission.updated_at
        if updated_at and (datetime.utcnow() - updated_at.replace(tzinfo=None)).total_seconds() < 900:
            raise HTTPException(409, "Mission is still marked as running; do not start a duplicate execution.")
        resumable_states.update({"RUNNING", "IN_PROGRESS"})
    if mission.approved_by != current_user.id or mission.status not in ({"PENDING"} | resumable_states):
        raise HTTPException(403, "Owner approval is required before starting or resuming this mission")
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
        if agent_id not in {definition.id for definition in AGENTS}:
            raise HTTPException(400, "Only a registered agent can propose work")
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
