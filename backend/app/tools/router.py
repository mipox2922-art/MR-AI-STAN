from __future__ import annotations

import re
from typing import Any

TOOL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("system_telemetry", ("cpu", "ram", "memory", "storage", "disk", "network", "uptime", "system", "mfumo", "hali ya pc")),
    ("searxng", ("tafuta", "search", "research", "habari", "google", "web", "mtandao", "jua kuhusu", "nipe taarifa")),
    ("browser_hands", ("browser", "chrome", "website", "web site", "youtube", "instagram", "facebook", "fungua", "bonyeza", "click", "type", "scroll", "navigate", "peruzi")),
    ("device_bridge", ("simu", "android", "adb", "fastboot", "usb", "bluetooth", "wifi", "device", "reboot", "flash")),
    ("creative_canvas", ("bango", "poster", "banner", "logo", "design", "graphic", "creative", "canvas", "picha")),
    ("tesseract", ("ocr", "soma maandishi", "screenshot", "scan image", "extract text")),
    ("ffmpeg", ("video", "audio", "convert media", "ffmpeg", "compress video")),
    ("whisper_local", ("transcribe", "transcription", "speech to text", "andika nilichosema")),
    ("gmail", ("gmail", "email", "mail", "barua pepe", "inbox", "reply email")),
    ("scheduler", ("schedule", "ratiba", "reminder", "kumbusha", "kesho", "kila siku", "every day")),
    ("memory", ("kumbuka", "remember", "memory", "sahau", "forget")),
    ("coding", ("code", "coding", "program", "repo", "github", "build", "bug", "debug", "website ya project")),
    ("security", ("security", "usalama", "vulnerability", "malware", "threat", "audit", "port scan")),
    ("openstreetmap", ("map", "ramani", "location", "locate me", "mahali nilipo")),
)

TOOL_META: dict[str, dict[str, Any]] = {
    "system_telemetry": {"execution": "BACKEND", "risk": "LOW"},
    "searxng": {"execution": "BACKEND", "risk": "LOW"},
    "browser_hands": {"execution": "LOCAL_HAND", "risk": "MEDIUM"},
    "device_bridge": {"execution": "LOCAL_HAND", "risk": "HIGH"},
    "creative_canvas": {"execution": "BROWSER_UI", "risk": "LOW"},
    "tesseract": {"execution": "LOCAL_BINARY", "risk": "LOW"},
    "ffmpeg": {"execution": "LOCAL_BINARY", "risk": "LOW"},
    "whisper_local": {"execution": "LOCAL_BINARY", "risk": "LOW"},
    "gmail": {"execution": "OAUTH", "risk": "MEDIUM"},
    "scheduler": {"execution": "BACKEND", "risk": "MEDIUM"},
    "memory": {"execution": "BACKEND", "risk": "LOW"},
    "coding": {"execution": "LOCAL_HAND", "risk": "MEDIUM"},
    "security": {"execution": "LOCAL_HAND", "risk": "HIGH"},
    "openstreetmap": {"execution": "BROWSER_UI", "risk": "LOW"},
}

def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-ZÀ-ÿ0-9_+-]+", text.casefold()))

def route_command(text: str) -> dict[str, Any]:
    request = str(text).strip()
    value = request.casefold()
    tokens = _tokens(request)

    scored: list[tuple[int, str, str]] = []
    for tool_id, keywords in TOOL_RULES:
        score = 0
        matched: list[str] = []
        for keyword in keywords:
            key = keyword.casefold()
            if " " in key:
                if key in value:
                    score += 3
                    matched.append(keyword)
            elif key in tokens:
                score += 2
                matched.append(keyword)
        if score:
            scored.append((score, tool_id, ", ".join(matched[:5])))

    scored.sort(key=lambda item: (-item[0], item[1]))

    if not scored:
        return {
            "status": "NO_TOOL_MATCH",
            "request": request,
            "tool": None,
            "execution": "AI_ONLY",
            "message": "No deterministic tool match. The AI can answer normally.",
        }

    score, tool_id, matched = scored[0]
    meta = TOOL_META[tool_id]
    return {
        "status": "ROUTED",
        "request": request,
        "tool": tool_id,
        "score": score,
        "matched_keywords": matched.split(", ") if matched else [],
        **meta,
    }
