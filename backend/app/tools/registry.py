from __future__ import annotations

import shutil
from typing import Any

from ..config import settings
from ..connectors.coding_workspace import coding_workspace_status

def _binary_status(binary: str, label: str) -> dict[str, Any]:
    path = shutil.which(binary)
    return {
        "id": label,
        "status": "READY" if path else "NOT_INSTALLED",
        "mode": "LOCAL",
        "binary": path,
    }

def get_tool_registry() -> list[dict[str, Any]]:
    return [
        {
            "id": "system_telemetry",
            "name": "System Telemetry",
            "category": "CORE",
            "status": "READY",
            "mode": "LOCAL",
            "free": True,
            "description": "CPU, memory, storage, network, uptime and optional GPU telemetry.",
        },
        {
            "id": "coding_workspace",
            "name": "GitHub Coding Workspace",
            "category": "CODING",
            "status": "CONNECTED" if coding_workspace_status().get("configured") else "NOT_CONNECTED",
            "mode": "GITHUB_API",
            "free": True,
            "description": "Restricted file inspection/commit operations on a configured non-production branch; completion is based on actual GitHub Actions checks.",
        },
        {
            "id": "browser_hands",
            "name": "Browser Hands",
            "category": "BROWSER",
            "status": "AVAILABLE",
            "mode": "LOCAL",
            "free": True,
            "description": "Available through the installed Chrome extension; connection state is verified when a browser action is requested.",
        },
        {
            "id": "device_bridge",
            "name": "Device Bridge",
            "category": "DEVICE",
            "status": "AVAILABLE",
            "mode": "LOCAL",
            "free": True,
            "description": "Local bridge capability; becomes operational when the protected bridge is running and paired.",
        },
        {
            "id": "openstreetmap",
            "name": "OpenStreetMap Map",
            "category": "MAP",
            "status": "READY",
            "mode": "WEB",
            "free": True,
            "description": "Open geographic map used by the Tracking Map panel.",
        },
        {
            "id": "street_view",
            "name": "Street View",
            "category": "MAP",
            "status": "AVAILABLE",
            "mode": "WEB_URL",
            "free": True,
            "description": "Available as a coordinate-based Maps URL; coverage depends on the target location.",
        },
        {
            "id": "device_tracking",
            "name": "Local Device Tracking",
            "category": "DEVICE",
            "status": "AVAILABLE",
            "mode": "LOCAL_SENSOR",
            "free": True,
            "description": "Available through the local bridge; results require real Wi-Fi, BLE or authorized Android sensor evidence.",
        },
        {
            "id": "browser_speech",
            "name": "Browser Speech",
            "category": "VOICE",
            "status": "READY",
            "mode": "BROWSER",
            "free": True,
            "description": "Browser SpeechRecognition and speechSynthesis without a paid voice service.",
        },
        {
            "id": "creative_canvas",
            "name": "HTML Canvas Studio",
            "category": "CREATIVE",
            "status": "READY",
            "mode": "BROWSER",
            "free": True,
            "description": "Editable poster/banner canvas with draggable layers and PNG export.",
        },
        {
            "id": "gemini",
            "name": "Gemini Provider",
            "category": "AI",
            "status": "CONNECTED" if settings.gemini_api_key else "NOT_CONNECTED",
            "mode": "CLOUD",
            "free": True,
            "tier": settings.gemini_tier,
            "description": "Primary AI provider. Uses the configured Gemini account and its available quota.",
        },
        {
            "id": "openrouter",
            "name": "OpenRouter Provider",
            "category": "AI",
            "status": "CONNECTED" if settings.openrouter_api_key else "NOT_CONNECTED",
            "mode": "CLOUD_API",
            "free": settings.openrouter_model == "openrouter/free" or settings.openrouter_model.endswith(":free"),
            "model": settings.openrouter_model,
            "description": "OpenAI-compatible AI gateway. The default free router selects an available free model; usage is subject to provider rate limits.",
        },
        {
            "id": "mistral",
            "name": "Mistral Provider",
            "category": "AI",
            "status": "CONNECTED" if settings.mistral_api_key else "NOT_CONNECTED",
            "mode": "CLOUD_API",
            "free": False,
            "model": settings.mistral_model,
            "description": "Mistral chat completion API; charges/limits depend on the linked Mistral account and model.",
        },
        {
            "id": "grok",
            "name": "Grok (xAI) Provider",
            "category": "AI",
            "status": "CONNECTED" if settings.xai_api_key else "NOT_CONNECTED",
            "mode": "CLOUD_API",
            "free": False,
            "model": settings.grok_model,
            "description": "Grok chat completion API; usage may be billed by xAI according to the account and selected model.",
        },
        {
            "id": "gmail",
            "name": "Gmail",
            "category": "COMMUNICATION",
            "status": "AVAILABLE" if settings.gmail_client_id and settings.gmail_client_secret and settings.gmail_redirect_uri else "NOT_CONFIGURED",
            "mode": "OAUTH",
            "free": True,
            "description": "Least-privilege Gmail OAuth connector for mailbox search/read. User authorization is required.",
        },
        {
            "id": "kimi",
            "name": "Kimi Provider",
            "category": "AI",
            "status": "CONNECTED" if settings.kimi_api_key else "NOT_CONNECTED",
            "mode": "CLOUD",
            "free": False,
            "description": "Secondary AI provider. Availability depends on the configured API account.",
        },
        {
            "id": "business_broker",
            "name": "Business Broker Pipeline",
            "category": "BUSINESS",
            "status": "AVAILABLE",
            "mode": "BACKEND",
            "free": True,
            "description": "Owner-scoped opportunity research, source evidence, transparent rule-based ranking, editable outreach drafts and persistent follow-up tasks. Search availability depends on configured public sources.",
        },
        {
            "id": "searxng",
            "name": "SearXNG Search",
            "category": "RESEARCH",
            "status": "CONNECTED" if settings.searxng_url else "AVAILABLE",
            "mode": "SELF_HOSTED_WITH_PUBLIC_FALLBACK",
            "free": True,
            "description": "Uses configured SearXNG when available; otherwise tries DuckDuckGo's public HTML search without an API key. Runtime success is reported only after live results are received.",
        },
        {
            **_binary_status("adb", "adb"),
            "name": "Android ADB",
            "category": "DEVICE",
            "free": True,
            "description": "Authorized Android debugging and diagnostics.",
        },
        {
            **_binary_status("fastboot", "fastboot"),
            "name": "Fastboot",
            "category": "DEVICE",
            "free": True,
            "description": "Authorized bootloader diagnostics and confirmed flashing workflows.",
        },
        {
            **_binary_status("tesseract", "tesseract"),
            "name": "Tesseract OCR",
            "category": "VISION",
            "free": True,
            "description": "Local OCR for extracting text from images and scans when installed.",
        },
        {
            **_binary_status("ffmpeg", "ffmpeg"),
            "name": "FFmpeg",
            "category": "MEDIA",
            "free": True,
            "description": "Local audio/video conversion and processing when installed.",
        },
        {
            "id": "whisper_local",
            "name": "Whisper Local",
            "category": "VOICE",
            "status": "OPTIONAL_NOT_INSTALLED",
            "mode": "LOCAL",
            "free": True,
            "description": "Optional local speech-to-text engine for stronger offline voice workflows.",
        },
        {
            "id": "playwright",
            "name": "Playwright",
            "category": "BROWSER",
            "status": "OPTIONAL_NOT_INSTALLED",
            "mode": "LOCAL",
            "free": True,
            "description": "Optional browser automation/test engine; install only when this environment needs it.",
        },
    ]

def registry_summary() -> dict[str, Any]:
    tools = get_tool_registry()
    return {
        "total": len(tools),
        "ready": sum(tool["status"] in {"READY", "CONNECTED"} for tool in tools),
        "available": sum(tool["status"] == "AVAILABLE" for tool in tools),
        "status_counts": {
            status: sum(tool["status"] == status for tool in tools)
            for status in sorted({tool["status"] for tool in tools})
        },
        "optional": sum(str(tool["status"]).startswith("OPTIONAL") for tool in tools),
        "not_connected": sum(tool["status"] == "NOT_CONNECTED" for tool in tools),
        "tools": tools,
    }
