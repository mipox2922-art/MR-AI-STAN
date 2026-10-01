from __future__ import annotations

import shutil
from typing import Any

from ..config import settings

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
            "id": "browser_hands",
            "name": "Browser Hands",
            "category": "BROWSER",
            "status": "READY",
            "mode": "LOCAL",
            "free": True,
            "description": "Authorized page read, click, type, scroll, navigate and drag through the Chrome extension.",
        },
        {
            "id": "device_bridge",
            "name": "Device Bridge",
            "category": "DEVICE",
            "status": "READY",
            "mode": "LOCAL",
            "free": True,
            "description": "Local bridge for authorized Android, Fastboot, Wi-Fi and BLE operations.",
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
            "free": False,
            "description": "Primary AI provider. Availability depends on the configured API account.",
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
            "id": "searxng",
            "name": "SearXNG Search",
            "category": "RESEARCH",
            "status": "CONNECTED" if settings.searxng_url else "OPTIONAL_NOT_CONFIGURED",
            "mode": "SELF_HOSTED",
            "free": True,
            "description": "Privacy-oriented metasearch through a configured self-hosted SearXNG instance.",
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
        "optional": sum(str(tool["status"]).startswith("OPTIONAL") for tool in tools),
        "not_connected": sum(tool["status"] == "NOT_CONNECTED" for tool in tools),
        "tools": tools,
    }
