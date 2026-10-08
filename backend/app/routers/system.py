from __future__ import annotations

import shutil
import subprocess
import time

import psutil
from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..database import engine

from ..config import settings
from ..dependencies import get_current_user

router = APIRouter(prefix="/system", tags=["System"])

def _gpu_status() -> dict:
    if not shutil.which("nvidia-smi"):
        return {"status": "UNAVAILABLE", "utilization_percent": None, "memory_percent": None}
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        util, used, total = [float(part.strip()) for part in result.stdout.strip().splitlines()[0].split(',')]
        return {
            "status": "ONLINE",
            "utilization_percent": round(util, 1),
            "memory_percent": round((used / total * 100), 1) if total else None,
        }
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return {"status": "UNAVAILABLE", "utilization_percent": None, "memory_percent": None}

def _database_status() -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        return "ONLINE"
    except Exception:
        return "OFFLINE"


def _service_status() -> dict:
    gemini_configured = bool(settings.gemini_api_key)
    kimi_configured = bool(settings.kimi_api_key)
    ai_ready = gemini_configured or kimi_configured

    return {
        "ai_core": "READY" if ai_ready else "NOT_CONFIGURED",
        "database": _database_status(),
        "memory": "ONLINE",
        "web_app": "ONLINE",
        "agents": "ONLINE",
        "voice": "NOT_CONFIGURED",
        "extension": "NOT_CONNECTED",
        "gemini": "CONFIGURED" if gemini_configured else "NOT_CONFIGURED",
        "kimi": "CONFIGURED" if kimi_configured else "NOT_CONFIGURED",
    }

@router.get('/status')
def system_status(current_user=Depends(get_current_user)):
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()
    return {
        "organization": {
            "owner": "Boss Ferisi",
            "manager": "MR AI",
            "workspace": "MOG343",
            "crew": "Agent Team",
            "model_role": "Digital Chief of Staff",
        },
        "services": _service_status(),
        "telemetry": {
            "cpu_percent": round(psutil.cpu_percent(interval=0.05), 1),
            "memory_percent": round(memory.percent, 1),
            "storage_percent": round(disk.percent, 1),
            "network": {"bytes_sent": net.bytes_sent, "bytes_received": net.bytes_recv},
            "gpu": _gpu_status(),
            "uptime_seconds": max(0, int(time.time() - psutil.boot_time())),
        },
        "security": {"threats_detected": None, "source": "no_security_engine"},
        "ai": {
            "provider": "gemini" if settings.gemini_api_key else ("kimi" if settings.kimi_api_key else None),
            "model": settings.gemini_model if settings.gemini_api_key else (settings.kimi_model if settings.kimi_api_key else None),
            "tier": settings.gemini_tier if settings.gemini_api_key else ("KIMI_CONFIGURED" if settings.kimi_api_key else None),
            "ready": bool(settings.gemini_api_key or settings.kimi_api_key),
        },
        "capabilities": {
            "street_view": "AVAILABLE_VIA_MAPS_URL",
            "device_tracking": "LOCAL_SENSOR_ONLY",
            "gemini_tier": settings.gemini_tier,
        },
    }
