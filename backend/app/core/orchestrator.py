from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from ..models import Execution, ActivityLog, ApprovalRequest, Task, TaskStep
from ..audit import record_safe_error
from .intent import classify
from .permissions import check_permission, create_approval


async def run(user_id: int, text: str, db: Session) -> dict:
    """Plan-only orchestrator. Every created task waits for explicit owner approval."""
    started = time.perf_counter()
    request = str(text or "").strip()
    if not request:
        return {"status": "INVALID", "reason": "request is required"}

    intent = classify(request)

    # Public job-feed research is read-only and does not submit applications.
    # Run it directly so a normal "tafuta kazi" request never becomes a
    # meaningless approval request that blocks the user's actual goal.
    if intent.name == "JOB_RESEARCH":
        query = re.sub(
            r"^(?:nitafutie|tafutia|tafuta|find(?: me)?|search(?: for)?|research|job research)\\b",
            "", request, flags=re.IGNORECASE,
        ).strip(" :,-")
        query = re.sub(
            r"^(?:nafasi za kazi|kazi|ajira|remote jobs?|jobs?)\\b",
            "", query, flags=re.IGNORECASE,
        )
        query = re.sub(r"^(?:za|ya|for|in)\\b", "", query, flags=re.IGNORECASE).strip()
        query = re.sub(r"\\s+(?:sawa\\s+fanya|sawa|fanya|tafadhali|please)\\s*$", "", query, flags=re.IGNORECASE).strip()
        query = query or "remote jobs"

        try:
            from ..routers.jobs import research_public_jobs
            job_result = await research_public_jobs(query, limit=15)
            feed_status = str(job_result.get("status") or "FAILED").upper()
            success = feed_status in {"COMPLETED", "NO_RESULTS"}
        except Exception as exc:
            feed_status = "FAILED"
            success = False
            job_result = {
                "status": "FAILED",
                "query": query,
                "count": 0,
                "results": [],
                "sources": ["RemoteOK", "Remotive"],
                "source_warnings": [type(exc).__name__],
                "note": "Public job feeds did not return a usable result. No application was submitted.",
            }

        task_status = "COMPLETED" if success else "FAILED"
        evidence_obj = {
            "tool": "public_job_feeds",
            "status": feed_status,
            "query": query,
            "count": int(job_result.get("count") or len(job_result.get("results") or [])),
            "sources": job_result.get("sources") or [],
            "source_warnings": job_result.get("source_warnings") or [],
            "sample_urls": [
                str(item.get("url") or "")
                for item in (job_result.get("results") or [])[:5]
                if isinstance(item, dict) and item.get("url")
            ],
            "verified": success,
            "note": "Utafiti wa vyanzo vya umma tu; hakuna maombi ya kazi yaliyotumwa.",
        }

        task = Task(
            user_id=user_id,
            title=f"Utafutaji wa kazi: {query}"[:255],
            description=request[:12000],
            status=task_status,
            priority="NORMAL",
            agent="jobs",
            source="orchestrator",
            requested_by="MR AI Job Research",
            progress=100 if success else 0,
            result=json.dumps(job_result, ensure_ascii=False, default=str),
            error=None if success else "Vyanzo vya kazi havikurudisha matokeo yanayoweza kutumika.",
        )
        db.add(task)
        db.flush()
        db.add(TaskStep(
            task_id=task.id,
            position=1,
            title="Tafuta nafasi za kazi kwenye vyanzo vya umma",
            state="verified" if success else "failed",
            evidence=json.dumps(evidence_obj, ensure_ascii=False, default=str),
            verified_at=datetime.now(timezone.utc).replace(tzinfo=None) if success else None,
        ))
        execution = Execution(
            user_id=user_id,
            intent="JOB_RESEARCH",
            status=task_status,
            risk="LOW",
            result=json.dumps({"task_id": task.id, "job_results": job_result}, ensure_ascii=False, default=str),
            error=None if success else task.error,
        )
        db.add(execution)
        db.add(ActivityLog(
            user_id=user_id,
            action="JOB_RESEARCH_AUTO_EXECUTED" if success else "JOB_RESEARCH_FAILED",
            details=f"task_id={task.id}; status={task_status}; query={query[:180]}; results={evidence_obj['count']}",
        ))
        db.commit()
        db.refresh(task)
        db.refresh(execution)
        return {
            "status": task_status,
            "execution_started": True,
            "execution_id": execution.id,
            "task_id": task.id,
            "intent": "JOB_RESEARCH",
            "risk": "LOW",
            "job_results": job_result,
            "task": {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "progress": task.progress,
                "agent": task.agent,
            },
            "next_action": (
                "Kagua nafasi na fungua tovuti ya mwajiri. Hakuna maombi yaliyotumwa."
                if success else
                "Vyanzo vya kazi vimeshindwa kujibu. Jaribu tena baadaye."
            ),
        }

    decision = check_permission(db, user_id, intent.name, intent.risk)

    execution = Execution(
        user_id=user_id,
        intent=intent.name,
        status="WAITING_APPROVAL",
        risk=intent.risk,
    )
    db.add(execution)
    db.flush()

    mission = Task(
        user_id=user_id,
        title=request[:255],
        description=request[:12000],
        status="WAITING_APPROVAL",
        priority="HIGH" if intent.risk in {"HIGH", "CRITICAL"} else "NORMAL",
        agent="orchestrator",
        source="orchestrator",
        requested_by="MR AI Orchestrator",
        progress=0,
    )
    db.add(mission)
    db.flush()

    # Use the actual planner registry. Planned steps stay pending until Boss approves.
    from ..orchestration.planner import build_plan
    plan = build_plan(request)
    for index, plan_step in enumerate(plan.get("steps") or [], start=1):
        db.add(TaskStep(
            task_id=mission.id,
            position=index,
            title=str(plan_step.get("name") or plan_step.get("agent") or f"Hatua {index}")[:255],
            state="pending",
            evidence=None,
        ))

    approval_payload = {
        "task_id": mission.id,
        "execution_id": execution.id,
        "intent": intent.name,
        "parameters": intent.parameters,
    }
    approval = ApprovalRequest(
        user_id=user_id,
        action=intent.name,
        payload=json.dumps(approval_payload, ensure_ascii=False, default=str),
        status="PENDING",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(approval)
    execution.error = decision.reason if decision.requires_approval else "Owner approval is mandatory for every orchestrator-created task."
    execution.result = json.dumps({
        "task_id": mission.id,
        "approval_id": None,
        "status": "WAITING_APPROVAL",
        "execution_started": False,
    }, ensure_ascii=False)
    db.add(ActivityLog(
        user_id=user_id,
        action="ORCHESTRATION_PROPOSED",
        details=f"task_id={mission.id}; execution_id={execution.id}; intent={intent.name}; risk={intent.risk}",
    ))
    db.commit()
    db.refresh(execution)
    db.refresh(mission)
    db.refresh(approval)

    execution.result = json.dumps({
        "task_id": mission.id,
        "approval_id": approval.id,
        "status": "WAITING_APPROVAL",
        "execution_started": False,
    }, ensure_ascii=False)
    db.commit()

    return {
        "status": "WAITING_APPROVAL",
        "execution_id": execution.id,
        "task_id": mission.id,
        "approval_id": approval.id,
        "intent": intent.name,
        "confidence": intent.confidence,
        "risk": intent.risk,
        "reason": "Boss Ferisi lazima aidhinishe kabla ya hatua yoyote kutekelezwa.",
        "execution_started": False,
        "plan": plan,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
