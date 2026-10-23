from __future__ import annotations

from typing import Any

from ..agents.registry import AGENTS


# These are execution specialties, not decorative dashboard labels. The
# orchestrator manages the mission; only the specialist that can do the work
# should appear as an executable step.
ROUTES = (
    (("cpu", "ram", "storage", "disk", "network", "uptime", "telemetry", "system status", "system health", "afya ya mfumo", "hali ya pc", "mfumo"), "orchestrator"),
    (("job", "jobs", "kazi", "ajira", "remote"), "jobs"),
    (("gmail", "email", "emails", "mail", "inbox", "barua pepe"), "gmail"),
    (("youtube", "instagram", "browser", "chrome", "open website", "fungua website", "peruzi", "tafuta mtandaoni", "soma ukurasa", "read page", "fungua", "bonyeza", "click", "andika", "type", "weka", "jaza", "scroll", "sogeza", "drag"), "browser"),
    (("bango", "poster", "banner", "graphic", "design", "logo"), "creative"),
    (("simu", "android", "adb", "fastboot", "bluetooth", "usb", "flash"), "device"),
    (("security", "usalama", "scan", "vulnerability", "port", "malware"), "security"),
    (("code", "coding", "program", "repo", "github", "app", "website", "tovuti", "build", "bug", "debug", "rekebisha"), "coding"),
    (("memory", "kumbuka", "sahau", "remember", "forget"), "memory"),
    (("schedule", "ratiba", "reminder", "kumbusha", "kesho", "kila siku"), "scheduler"),
)


def select_agents(text: str) -> list[str]:
    value = str(text or "").casefold()
    selected: list[str] = []
    for keywords, agent_id in ROUTES:
        if any(keyword in value for keyword in keywords) and agent_id not in selected:
            selected.append(agent_id)

    # Generic research is a fallback only. Never silently add an orchestrator
    # telemetry step to unrelated work.
    if not selected:
        selected.append("research")
    return selected


def build_plan(text: str) -> dict[str, Any]:
    request = str(text or "").strip()
    definitions = {agent.id: agent for agent in AGENTS}
    agent_ids = select_agents(request)
    steps = []

    for index, agent_id in enumerate(agent_ids, start=1):
        agent = definitions[agent_id]
        steps.append({
            "step": index,
            "agent": agent.id,
            "name": agent.name,
            "risk": agent.risk,
            "capabilities": list(agent.capabilities),
            "tools": list(agent.tools),
            "status": "PLANNED",
        })

    return {
        "request": request,
        "status": "PLANNED",
        "agents": [definitions[item].name for item in agent_ids],
        "steps": steps,
        "verification": [
            "Every external action must return a verified result from its actual execution tool.",
            "A queued browser/device handoff is not proof that the remote action completed.",
            "Persist each step's tool, result, failure or verification evidence.",
            "A mission is complete only when every required step is verified.",
        ],
    }
