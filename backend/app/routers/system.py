from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timezone

try:
    import psutil
except ImportError:
    psutil = None
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
    openrouter_configured = bool(settings.openrouter_api_key)
    mistral_configured = bool(settings.mistral_api_key)
    grok_configured = bool(settings.xai_api_key)
    ai_ready = any((gemini_configured, kimi_configured, openrouter_configured, mistral_configured, grok_configured))

    return {
        "ai_core": "CONFIGURED" if ai_ready else "NOT_CONFIGURED",
        "database": _database_status(),
        "memory": "ONLINE",
        "web_app": "ONLINE",
        "agents": "REGISTERED",
        "web_search": "CONFIGURED" if settings.searxng_url else "AVAILABLE",
        "security": "NOT_CONFIGURED",
        "voice": "NOT_CONFIGURED",
        "extension": "NOT_CONNECTED",
        "gemini": "CONFIGURED" if gemini_configured else "NOT_CONFIGURED",
        "kimi": "CONFIGURED" if kimi_configured else "NOT_CONFIGURED",
        "openrouter": "CONFIGURED" if openrouter_configured else "NOT_CONFIGURED",
        "mistral": "CONFIGURED" if mistral_configured else "NOT_CONFIGURED",
        "grok": "CONFIGURED" if grok_configured else "NOT_CONFIGURED",
    }

def _default_ai_provider() -> tuple[str | None, str | None, str | None]:
    """Prefer explicitly free AI routes before any provider that may incur charges."""
    openrouter_key = settings.openrouter_api_key.strip()
    openrouter_model = settings.openrouter_model.strip()
    normalized_model = openrouter_model.lower()
    openrouter_free = bool(openrouter_key) and (
        normalized_model == "openrouter/free" or normalized_model.endswith(":free")
    )
    gemini_key = settings.gemini_api_key.strip()
    gemini_free = bool(gemini_key) and settings.gemini_tier.strip().upper() == "FREE"

    if openrouter_free:
        return "openrouter", openrouter_model, "OPENROUTER_FREE"
    if gemini_free:
        return "gemini", settings.gemini_model, "FREE"
    if openrouter_key:
        return "openrouter", openrouter_model, "OPENROUTER_CONFIGURED"
    if settings.mistral_api_key.strip():
        return "mistral", settings.mistral_model, "MISTRAL_CONFIGURED"
    if settings.xai_api_key.strip():
        return "grok", settings.grok_model, "GROK_CONFIGURED"
    if gemini_key:
        return "gemini", settings.gemini_model, settings.gemini_tier
    if settings.kimi_api_key.strip():
        return "kimi", settings.kimi_model, "KIMI_CONFIGURED"
    return None, None, None


@router.get("/status")
def system_status(current_user=Depends(get_current_user)):
    if psutil is None:
        telemetry = {
            "cpu_percent": None,
            "memory_percent": None,
            "storage_percent": None,
            "network": {"bytes_sent": None, "bytes_received": None},
            "gpu": {
                "status": "UNAVAILABLE",
                "utilization_percent": None,
                "memory_percent": None,
            },
            "uptime_seconds": None,
            "source": "serverless_runtime",
        }
    else:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        telemetry = {
            "cpu_percent": round(psutil.cpu_percent(interval=0.05), 1),
            "memory_percent": round(memory.percent, 1),
            "storage_percent": round(disk.percent, 1),
            "network": {"bytes_sent": net.bytes_sent, "bytes_received": net.bytes_recv},
            "gpu": _gpu_status(),
            "uptime_seconds": max(0, int(time.time() - psutil.boot_time())),
            "source": "host_runtime",
        }
    selected_provider, selected_model, selected_tier = _default_ai_provider()

    return {
        "organization": {
            "owner": "Boss Ferisi",
            "manager": "MR AI",
            "workspace": "MOG343",
            "crew": "Agent Team",
            "model_role": "Digital Chief of Staff",
        },
        "services": _service_status(),
        "telemetry": telemetry,
        "security": {"threats_detected": None, "source": "no_security_engine"},
        "ai": {
            "provider": selected_provider,
            "model": selected_model,
            "tier": selected_tier,
            "configured": selected_provider is not None,
            "ready": False,
        },
        "capabilities": {
            "street_view": "AVAILABLE_VIA_MAPS_URL",
            "device_tracking": "LOCAL_SENSOR_ONLY",
            "gemini_tier": settings.gemini_tier,
        },
    }


@router.get("/diagnostics")
def system_diagnostics(current_user=Depends(get_current_user)):
    """Report configuration and reachability checks without exposing secrets."""
    database = _database_status()
    providers = {
        "OpenRouter": bool(settings.openrouter_api_key),
        "Gemini": bool(settings.gemini_api_key),
        "Kimi": bool(settings.kimi_api_key),
        "Mistral": bool(settings.mistral_api_key),
        "Grok": bool(settings.xai_api_key),
    }
    configured = [name for name, is_configured in providers.items() if is_configured]
    gmail_configured = all((
        settings.gmail_client_id,
        settings.gmail_client_secret,
        settings.gmail_redirect_uri,
    ))
    checks = [
        {
            "id": "database",
            "label": "Persistent database",
            "status": "PASS" if database == "ONLINE" else "FAIL",
            "detail": "Database connection succeeded." if database == "ONLINE" else "Database connection failed; tasks and memory may be unavailable.",
        },
        {
            "id": "ai_provider",
            "label": "AI provider configuration",
            "status": "CONFIGURED" if configured else "MISSING",
            "detail": (
                "Configured keys: " + ", ".join(configured) + ". Keys are present but a live model call has not been tested by this check."
                if configured else
                "No AI provider key is configured. Chat cannot call a model until one is added."
            ),
        },
        {
            "id": "job_research",
            "label": "Job Research",
            "status": "AVAILABLE",
            "detail": "RemoteOK and Remotive public feeds are implemented; source reachability is checked when a search runs.",
        },
        {
            "id": "web_search",
            "label": "Research sources",
            "status": "CONFIGURED" if settings.searxng_url else "AVAILABLE",
            "detail": "SearXNG is configured for metasearch." if settings.searxng_url else "General research uses bounded public Wikipedia and Hacker News APIs. This is a limited fallback, not full-web metasearch.",
        },
        {
            "id": "gmail",
            "label": "Gmail OAuth",
            "status": "CONFIGURED" if gmail_configured else "NOT_CONFIGURED",
            "detail": "OAuth settings are present; mailbox authorization still needs its own connection check." if gmail_configured else "Gmail OAuth credentials are incomplete; Gmail actions stay unavailable.",
        },
        {
            "id": "scheduler",
            "label": "Render in-process scheduler",
            "status": (
                "ENABLED"
                if settings.scheduler_enabled and not settings.serverless_mode
                else "DISABLED"
            ),
            "detail": (
                "The scheduler loop runs inside the Render backend while the instance is awake."
                if settings.scheduler_enabled and not settings.serverless_mode
                else "The in-process scheduler is disabled by configuration."
            ),
        },
        {
            "id": "scheduler_wakeup",
            "label": "Optional GitHub Actions wake-up trigger",
            "status": (
                "RENDER_SECRET_CONFIGURED"
                if len(settings.cloudflare_cron_secret.strip()) >= 32
                else "OPTIONAL_NOT_CONFIGURED"
            ),
            "detail": (
                "A trigger secret is configured on Render. This diagnostic cannot confirm that GitHub Actions has the matching secret."
                if len(settings.cloudflare_cron_secret.strip()) >= 32
                else "Not required while the Render backend stays awake. If the instance sleeps, queued work pauses until it wakes; GitHub Actions can provide an optional authenticated trigger."
            ),
        },
        {
            "id": "device_bridge",
            "label": "Local PC / device bridge",
            "status": "LOCAL_ONLY",
            "detail": "A hosted server cannot verify a bridge on the owner's PC. Check this from the local dashboard after starting the Device Bridge.",
        },
        {
            "id": "host_telemetry",
            "label": "Host telemetry",
            "status": "AVAILABLE" if psutil is not None else "LIMITED",
            "detail": "Metrics describe the hosted backend, not the owner's PC." if psutil is not None else "Host telemetry library is unavailable.",
        },
    ]
    has_blocker = database != "ONLINE" or not configured
    return {
        "status": "DEGRADED" if has_blocker else "CONFIGURATION_CHECKED",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "truth_boundary": "This checks database reachability and configuration only. Provider keys, OAuth, public job feeds, and external hands need their own live execution to be marked verified.",
    }
