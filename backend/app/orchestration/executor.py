from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
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


def _is_read_only_gmail_request(request: str) -> bool:
    value = request.casefold()
    write_intents = (
        "send ", "send email", "tuma ", "tuma email", "tuma barua",
        "reply", "jibu", "forward", "sambaza", "delete", "futa email",
        "archive", "purchase", "pay",
    )
    if any(term in value for term in write_intents):
        return False
    read_intents = (
        "read", "soma", "search", "tafuta", "inbox", "angalia", "onyesha",
        "show", "check", "email zangu", "barua pepe zangu", "gmail",
    )
    return any(term in value for term in read_intents)


def _is_safe_for_autonomous_execution(
    plan: dict[str, Any],
    request: str,
    user_id: int,
    db: Session,
) -> bool:
    """Allow unattended execution only for implemented, read-only operations with live tools."""
    steps = plan.get("steps") or []
    if not steps:
        return False
    for step in steps:
        agent_id = step.get("agent")
        tools = set(step.get("tools") or [])
        # Public job feeds are read-only and never submit an application.
        if agent_id == "jobs":
            continue
        # Host telemetry is read-only and executed by this backend.
        if agent_id == "orchestrator" and "system_telemetry" in tools:
            continue
        # Research is automatic only if an actual search backend is configured.
        if agent_id == "research" and "searxng" in tools and settings.searxng_url:
            continue
        # Gmail reads are automatic only when OAuth is currently connected.
        if agent_id == "gmail" and _is_read_only_gmail_request(request):
            try:
                from ..connectors.gmail import connection_status
                if connection_status(db, user_id).get("connected") is True:
                    continue
            except Exception:
                pass
        # Unconnected or side-effecting tools do not get simulated.
        return False
    return True


def _web_search_query(request: str) -> str:
    value = request.strip()
    value = re.sub(
        r"^(?:tafuta(?:\s+mtandaoni)?|search(?:\s+(?:the\s+web|online|for))?|research|jua\s+kuhusu|nipe\s+taarifa(?:\s+kuhusu)?|onyesha)\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip(" :,-")[:300] or request.strip()[:300]


def _gmail_search_query(request: str) -> str:
    value = request.casefold()
    if any(term in value for term in ("unread", "zisizosomwa", "ambazo sijasoma")):
        return "in:inbox is:unread"
    if any(term in value for term in ("leo", "today")):
        return "in:inbox newer_than:1d"

    original = request.strip()
    query = re.sub(
        r"^(?:tafuta|search|find|read|soma|onyesha|show|angalia|check)\s+"
        r"(?:email(?:s)?|mail|gmail|barua\s+pepe)\b",
        "",
        original,
        flags=re.IGNORECASE,
    ).strip(" :,-")
    query = re.sub(r"^(?:zangu|yangu|zote|yote|za\s+leo|yangu\s+zote)\b", "", query, flags=re.IGNORECASE).strip()
    if query and query.casefold() not in {"zangu", "yangu", "zote", "yote", "za leo", "zangu za leo"}:
        return f"in:inbox {query}"[:500]
    return "in:inbox"


def _persist_step_progress(db: Session, mission: Task, steps: list[dict[str, Any]]) -> None:
    """Persist tool/action evidence as each step finishes so interrupted missions can resume."""
    total = max(len(steps), 1)
    existing = {
        row.position: row
        for row in db.query(TaskStep).filter(TaskStep.task_id == mission.id).all()
    }
    verified_total = 0
    for index, item in enumerate(steps, start=1):
        status = str(item.get("status") or "WAITING").upper()
        output = item.get("evidence")
        verified = status == "COMPLETED" and item.get("verified") is True and bool(output)
        evidence = json.dumps({
            "task_id": mission.id,
            "agent": item.get("agent"),
            "tool": item.get("tool"),
            "execution_status": status,
            "verified": verified,
            "output": output,
            "step_result": item,
        }, ensure_ascii=False, default=str)
        row = existing.get(index)
        if row is None:
            row = TaskStep(task_id=mission.id, position=index, title=str(item.get("name") or item.get("agent") or f"Step {index}")[:255])
            db.add(row)
            existing[index] = row
        row.title = str(item.get("name") or item.get("agent") or f"Step {index}")[:255]
        row.state = "verified" if verified else "failed" if status == "FAILED" else "pending"
        row.evidence = evidence
        row.verified_at = datetime.now(timezone.utc).replace(tzinfo=None) if verified else None
        verified_total += int(verified)

    mission.progress = int(verified_total / total * 100) if steps else 0
    mission.result = json.dumps({
        "steps": steps,
        "verified_steps": verified_total,
        "total_steps": len(steps),
    }, ensure_ascii=False, default=str)
    db.commit()
    db.refresh(mission)


def _resume_verified_step(db: Session, mission: Task, position: int) -> dict[str, Any] | None:
    row = db.query(TaskStep).filter(TaskStep.task_id == mission.id, TaskStep.position == position).first()
    if not row or str(row.state or "").lower() != "verified" or not row.evidence:
        return None
    try:
        payload = json.loads(row.evidence)
    except (TypeError, ValueError):
        return None
    # Only the executor's own structured evidence can be reused. Client handoffs
    # and legacy/manual evidence do not independently prove a tool action.
    if not isinstance(payload, dict) or payload.get("verified") is not True:
        return None
    previous = payload.get("step_result")
    if not isinstance(previous, dict) or str(previous.get("status", "")).upper() != "COMPLETED":
        return None
    return previous


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
        auto_execute = _is_safe_for_autonomous_execution(plan, request, user.id, db)
        proposed = Task(
            user_id=user.id,
            title=request[:255],
            description=request,
            status="PENDING" if auto_execute else "WAITING_APPROVAL",
            priority="NORMAL",
            agent="orchestrator",
            source="orchestrator",
            requested_by="MR AI Orchestrator",
            approved_by=user.id if auto_execute else None,
            progress=0,
        )
        db.add(proposed)
        db.flush()
        _add_steps_from_plan(db, proposed.id, plan)

        if auto_execute:
            db.add(ActivityLog(
                user_id=user.id,
                action="MISSION_AUTO_AUTHORIZED",
                details=f"task_id={proposed.id}; policy=read_only_verified_operations; steps={len(plan.get('steps') or [])}",
            ))
            db.commit()
            db.refresh(proposed)
            # Re-enter through the same executor path used by approved missions;
            # only the narrow allowlist above can take this route.
            return await execute_mission(request, user, db, mission=proposed)

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
                "evidence": {"message": "Imependekezwa na Orchestrator; inasubiri idhini kwa sababu hatua zake si za kusoma tu."},
            } for index, item in enumerate(plan.get("steps") or [], start=1)],
            "next_action": "Boss Ferisi akague mpango kisha aidhinishe. Hakuna kitendo cha nje kilichotekelezwa.",
        }

    if mission.user_id != user.id or mission.agent != "orchestrator":
        return {"status": "REJECTED", "reason": "Mission owner/agent did not match."}
    resumable_states = {"WAITING", "WAITING_FOR_HAND", "WAITING_FOR_VERIFICATION", "FAILED"}
    if mission.approved_by != user.id or mission.status not in ({"PENDING"} | resumable_states):
        return {"status": "WAITING_APPROVAL", "mission": _task_payload(mission),
                "next_action": "Boss approval is required before any mission step executes."}

    is_resume = mission.status in resumable_states
    mission.status = "RUNNING"
    mission.error = None
    db.add(ActivityLog(
        user_id=user.id,
        action="MISSION_RESUMED" if is_resume else "MISSION_STARTED",
        details=f"task_id={mission.id}; approved_by={user.id}; resume={is_resume}",
    ))
    db.commit()
    db.refresh(mission)

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
            evidence = system_status(user)
            steps.append({"step": index, "agent": agent_id, "name": step_name,
                "tool": "system_telemetry", "status": "COMPLETED", "verified": True,
                "evidence": evidence})
            _persist_step_progress(db, mission, steps)
            continue

        if agent_id == "research" and "searxng" in step.get("tools", []):
            if not settings.searxng_url:
                steps.append({"step": index, "agent": agent_id, "name": step_name,
                    "tool": "searxng", "status": "NOT_CONNECTED", "verified": False,
                    "evidence": {"message": "SearXNG is not configured; web research was not executed."}})
            else:
                query = _web_search_query(request)
                try:
                    from ..routers.tools import _search_searxng
                    result = await _search_searxng(query)
                    successful = str(result.get("status", "")).upper() == "COMPLETED"
                    steps.append({"step": index, "agent": agent_id, "name": step_name,
                        "tool": "searxng", "status": "COMPLETED" if successful else str(result.get("status", "FAILED")).upper(),
                        "verified": successful, "evidence": {
                            "query": query,
                            "source": result.get("source"),
                            "result_count": len(result.get("results") or []),
                            "results": (result.get("results") or [])[:10],
                            "message": "Live search results received from configured SearXNG." if successful else result.get("message", "Search did not complete."),
                        }})
                except Exception as exc:
                    steps.append({"step": index, "agent": agent_id, "name": step_name, "tool": "searxng",
                        "status": "FAILED", "verified": False,
                        "evidence": {"query": query, "message": f"Web research failed: {type(exc).__name__}."}})
            _persist_step_progress(db, mission, steps)
            continue

        if agent_id == "gmail":
            from ..connectors.gmail import GmailConnectorError, connection_status, list_messages
            try:
                state = connection_status(db, user.id)
                if state.get("connected") is not True:
                    steps.append({"step": index, "agent": agent_id, "name": step_name, "tool": "gmail",
                        "status": "NOT_CONNECTED", "verified": False,
                        "evidence": {"message": "Gmail OAuth is not connected for this user; no mail was read."}})
                elif not _is_read_only_gmail_request(request):
                    steps.append({"step": index, "agent": agent_id, "name": step_name, "tool": "gmail",
                        "status": "WAITING_APPROVAL", "verified": False,
                        "evidence": {"message": "This request may send or modify email. The current Gmail workflow requires an explicit send/reply confirmation and structured recipient/content."}})
                else:
                    query = _gmail_search_query(request)
                    result = await list_messages(db, user.id, query=query, max_results=20)
                    messages = result.get("messages") or []
                    steps.append({"step": index, "agent": agent_id, "name": step_name, "tool": "gmail",
                        "status": "COMPLETED" if str(result.get("status", "")).upper() == "COMPLETED" else "FAILED",
                        "verified": str(result.get("status", "")).upper() == "COMPLETED",
                        "evidence": {
                            "query": query,
                            "count": len(messages),
                            "result_size_estimate": result.get("result_size_estimate", len(messages)),
                            "messages": messages,
                            "message": "Messages fetched from the authenticated Gmail API; no messages were modified.",
                        }})
            except GmailConnectorError as exc:
                steps.append({"step": index, "agent": agent_id, "name": step_name, "tool": "gmail",
                    "status": "FAILED", "verified": False,
                    "evidence": {"message": str(exc)[:400]}})
            except Exception as exc:
                steps.append({"step": index, "agent": agent_id, "name": step_name, "tool": "gmail",
                    "status": "FAILED", "verified": False,
                    "evidence": {"message": f"Gmail read failed: {type(exc).__name__}."}})
            _persist_step_progress(db, mission, steps)
            continue

        if is_resume:
            previous = _resume_verified_step(db, mission, index)
            if previous is not None:
                steps.append(previous)
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

    # Every completed tool action has already been persisted. Persist any remaining
    # result rows (including a handoff) before deriving the final mission state.
    _persist_step_progress(db, mission, steps)
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
    if all_verified:
        mission.status = "COMPLETED"
    elif failed:
        mission.status = "FAILED"
    elif any(str(row.get("status", "")).upper() in {"WAITING_FOR_HAND", "NOT_CONNECTED"} for row in steps):
        mission.status = "WAITING_FOR_HAND"
    elif waiting:
        mission.status = "WAITING_FOR_VERIFICATION"
    else:
        mission.status = "VERIFYING"
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
