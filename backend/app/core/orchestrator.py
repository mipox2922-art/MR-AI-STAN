from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from ..models import Execution, ActivityLog, ApprovalRequest, Task, TaskStep
from ..audit import record_safe_error
from .intent import classify


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
        words = request.strip(" :,-").split()
        prefixes = (
            ("nitafutie",), ("tafutia",), ("tafuta",),
            ("find", "me"), ("find",), ("search", "for"), ("search",),
            ("research",), ("job", "research"),
        )
        lowered = [word.casefold() for word in words]
        for prefix in prefixes:
            if tuple(lowered[:len(prefix)]) == prefix:
                words = words[len(prefix):]
                lowered = lowered[len(prefix):]
                break

        job_prefixes = (
            ("nafasi", "za", "kazi"), ("remote", "jobs"), ("remote", "job"),
            ("kazi",), ("ajira",), ("jobs",), ("job",),
        )
        for prefix in job_prefixes:
            if tuple(lowered[:len(prefix)]) == prefix:
                words = words[len(prefix):]
                lowered = lowered[len(prefix):]
                break
        while lowered and lowered[0] in {"za", "ya", "for", "in"}:
            words.pop(0)
            lowered.pop(0)
        while lowered and lowered[-1] in {"sawa", "fanya", "tafadhali", "please"}:
            words.pop()
            lowered.pop()
        query = " ".join(words).strip() or "remote jobs"

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

        # Reuse the matching pending task if the same command was previously
        # blocked by the old generic approval gate. Avoid leaving the Boss's
        # already-requested job search stranded as a waiting approval.
        candidates = (
            db.query(Task)
            .filter(
                Task.user_id == user_id,
                Task.agent == "orchestrator",
                Task.status == "WAITING_APPROVAL",
            )
            .order_by(Task.id.desc())
            .all()
        )
        task = next(
            (
                item for item in candidates
                if (item.description or "").strip().casefold() == request.casefold()
            ),
            None,
        )
        reused_pending_task = task is not None
        if task is None:
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
            execution = Execution(
                user_id=user_id,
                intent="JOB_RESEARCH",
                status=task_status,
                risk="LOW",
                result=json.dumps({"task_id": task.id, "job_results": job_result}, ensure_ascii=False, default=str),
                error=None if success else task.error,
            )
            db.add(execution)
        else:
            # Repeated read-only request: finish that exact task, not a duplicate.
            db.query(TaskStep).filter(TaskStep.task_id == task.id).delete(synchronize_session=False)
            task.title = f"Utafutaji wa kazi: {query}"[:255]
            task.description = request[:12000]
            task.status = task_status
            task.priority = "NORMAL"
            task.agent = "jobs"
            task.source = "orchestrator"
            task.requested_by = "MR AI Job Research"
            task.progress = 100 if success else 0
            task.result = json.dumps(job_result, ensure_ascii=False, default=str)
            task.error = None if success else "Vyanzo vya kazi havikurudisha matokeo yanayoweza kutumika."

            # Cancel only approval/execution records tied to the exact task.
            for approval in db.query(ApprovalRequest).filter(
                ApprovalRequest.user_id == user_id,
                ApprovalRequest.status == "PENDING",
            ).all():
                try:
                    approval_payload = json.loads(approval.payload or "{}")
                except (TypeError, ValueError):
                    approval_payload = {}
                if str(approval_payload.get("task_id", "")) == str(task.id):
                    approval.status = "CANCELLED"
                    approval.resolved_at = datetime.utcnow()

            execution = None
            for existing_execution in db.query(Execution).filter(
                Execution.user_id == user_id,
                Execution.status == "WAITING_APPROVAL",
            ).order_by(Execution.id.desc()).all():
                try:
                    execution_payload = json.loads(existing_execution.result or "{}")
                except (TypeError, ValueError):
                    execution_payload = {}
                if str(execution_payload.get("task_id", "")) == str(task.id):
                    execution = existing_execution
                    break
            if execution is None:
                execution = Execution(
                    user_id=user_id,
                    intent="JOB_RESEARCH",
                    status=task_status,
                    risk="LOW",
                )
                db.add(execution)
            execution.intent = "JOB_RESEARCH"
            execution.status = task_status
            execution.risk = "LOW"
            execution.result = json.dumps({"task_id": task.id, "job_results": job_result}, ensure_ascii=False, default=str)
            execution.error = None if success else task.error

        db.flush()
        db.add(TaskStep(
            task_id=task.id,
            position=1,
            title="Tafuta nafasi za kazi kwenye vyanzo vya umma",
            state="verified" if success else "failed",
            evidence=json.dumps(evidence_obj, ensure_ascii=False, default=str),
            verified_at=datetime.now(timezone.utc).replace(tzinfo=None) if success else None,
        ))
        db.add(ActivityLog(
            user_id=user_id,
            action="JOB_RESEARCH_AUTO_EXECUTED" if success else "JOB_RESEARCH_FAILED",
            details=f"task_id={task.id}; reused_pending={reused_pending_task}; status={task_status}; query={query[:180]}; results={evidence_obj['count']}",
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


    # The chat endpoint must use the same execution engine as the Agents panel.
    # Creating an approval-only shell here used to strand every non-job command.
    from types import SimpleNamespace
    from ..orchestration.executor import execute_mission

    try:
        result = await execute_mission(request, SimpleNamespace(id=user_id), db)
        mission = result.get("mission") if isinstance(result, dict) else {}
        mission = mission if isinstance(mission, dict) else {}
        status = str(result.get("status", "FAILED")).upper()
        execution = Execution(
            user_id=user_id,
            intent=intent.name,
            status=status,
            risk=intent.risk,
            result=json.dumps({
                "task_id": mission.get("id"),
                "mission_status": status,
                "execution_started": status not in {"WAITING_APPROVAL", "REJECTED"},
                "mission_result": result,
            }, ensure_ascii=False, default=str),
            error=str(result.get("reason") or "")[:2000] or None,
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        result["execution_id"] = execution.id
        result["task_id"] = mission.get("id")
        result["intent"] = intent.name
        result["risk"] = intent.risk
        result["execution_started"] = status not in {"WAITING_APPROVAL", "REJECTED"}
        return result
    except Exception as exc:
        db.rollback()
        failure = Execution(
            user_id=user_id,
            intent=intent.name,
            status="FAILED",
            risk=intent.risk,
            error=f"Mission execution failed: {type(exc).__name__}",
            result=json.dumps({
                "status": "FAILED",
                "intent": intent.name,
                "reason": f"Execution raised {type(exc).__name__}; no success is claimed.",
            }, ensure_ascii=False),
        )
        db.add(failure)
        db.add(ActivityLog(
            user_id=user_id,
            action="ORCHESTRATION_FAILED",
            details=f"intent={intent.name}; error_type={type(exc).__name__}",
        ))
        db.commit()
        db.refresh(failure)
        return {
            "status": "FAILED",
            "execution_id": failure.id,
            "intent": intent.name,
            "risk": intent.risk,
            "execution_started": False,
            "reason": f"Mission execution failed: {type(exc).__name__}",
        }
