from __future__ import annotations

import time
from typing import Any
import httpx
try:
    import psutil
except ImportError:
    psutil = None

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Memory, Task
from .intent import Intent

async def execute(intent: Intent, user_id: int, db: Session) -> dict[str, Any]:
    started = time.perf_counter()

    if intent.name == "SYSTEM_INFO":
        if psutil is None:
            result = {
                "status": "NOT_AVAILABLE",
                "source": "serverless_runtime",
                "reason": "OS telemetry is not exposed in this runtime",
                "telemetry": {
                    "cpu_percent": None,
                    "memory_percent": None,
                    "storage_percent": None,
                    "network": {"bytes_sent": None, "bytes_received": None},
                },
            }
        else:
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            result = {
                "status": "COMPLETED",
                "source": "psutil",
                "telemetry": {
                    "cpu_percent": psutil.cpu_percent(interval=0.05),
                    "memory_percent": memory.percent,
                    "storage_percent": disk.percent,
                    "network": {"bytes_sent": net.bytes_sent, "bytes_received": net.bytes_recv},
                },
            }
    elif intent.name == "MEMORY_SEARCH":
        q = intent.parameters.get("query", "")
        rows = db.query(Memory).filter(Memory.user_id == user_id).all()
        result = {"status": "COMPLETED", "matches": [{"id": r.id, "key": r.key, "value": r.value} for r in rows if q in f"{r.key} {r.value}".casefold()]}
    elif intent.name == "MEMORY_SAVE":
        value = intent.parameters.get("query", "")
        row = Memory(user_id=user_id, key="conversation_memory", value=value)
        db.add(row)
        db.commit()
        db.refresh(row)
        result = {"status": "COMPLETED", "memory_id": row.id}
    elif intent.name == "TASK_CREATE":
        title = intent.parameters.get("query", "MR AI task")
        row = Task(user_id=user_id, title=title[:255], description=title, status="PENDING", priority="NORMAL")
        db.add(row)
        db.commit()
        db.refresh(row)
        result = {"status": "COMPLETED", "task_id": row.id, "task_status": row.status}
    elif intent.name == "WEB_RESEARCH":
        if not settings.searxng_url:
            return {"status": "NOT_CONNECTED", "reason": "SEARXNG_URL is not configured", "query": intent.parameters.get("query", "")}
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(settings.searxng_url.rstrip("/") + "/search", params={"q": intent.parameters.get("query", ""), "format": "json"})
            response.raise_for_status()
            data = response.json()
        result = {"status": "COMPLETED", "source": "configured_searxng", "results": data.get("results", [])[:10]}
    else:
        return {"status": "UNSUPPORTED", "reason": f"No execution hand for {intent.name}"}

    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return result
