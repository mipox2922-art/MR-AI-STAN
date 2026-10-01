from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..agents.registry import AGENTS


ROUTES = (
    (("job", "jobs", "kazi", "ajira", "remote"), "jobs"),
    (("gmail", "email", "barua pepe", "mail"), "gmail"),
    (("youtube", "instagram", "website", "browser", "peruzi", "tafuta mtandaoni"), "browser"),
    (("bango", "poster", "banner", "graphic", "design", "logo"), "creative"),
    (("simu", "android", "adb", "fastboot", "bluetooth", "usb", "flash"), "device"),
    (("security", "usalama", "scan", "vulnerability", "port", "malware"), "security"),
    (("code", "coding", "program", "repo", "github", "app", "website", "build"), "coding"),
    (("memory", "kumbuka", "sahau"), "memory"),
)


def select_agents(text: str) -> list[str]:
    value = text.casefold()
    selected: list[str] = ["orchestrator"]
    for keywords, agent_id in ROUTES:
        if any(keyword in value for keyword in keywords) and agent_id not in selected:
            selected.append(agent_id)
    if len(selected) == 1:
        selected.append("research")
    return selected


def build_plan(text: str) -> dict[str, Any]:
    agent_ids = select_agents(text)
    definitions = {agent.id: agent for agent in AGENTS}
    steps = []
    for index, agent_id in enumerate(agent_ids, start=1):
        agent = definitions[agent_id]
        steps.append({
            "step": index,
            "agent": agent.id,
            "name": agent.name,
            "risk": agent.risk,
            "capabilities": list(agent.capabilities),
            "status": "PLANNED",
        })
    return {
        "request": text.strip(),
        "status": "PLANNED",
        "agents": [definitions[item].name for item in agent_ids],
        "steps": steps,
        "verification": [
            "Every external action must return a verified result.",
            "High-risk device/security actions require an explicit authorization boundary.",
            "The system must never report completion without evidence.",
        ],
    }
