from __future__ import annotations

import re
from typing import Any

from ..agents.registry import AGENTS


# Route on the action phrase, not arbitrary nouns in the user's data. This
# prevents a memory payload such as "I like graphic design jobs" from
# accidentally launching three unrelated agents.
_COMMAND_ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("memory", (
        r"^(?:hifadhi\s+kumbukumbu|remember\s+this|remember\s+that|save\s+memory|kumbuka(?:\s+hii|\s+kwamba)?|unakumbuka|remember|sahau|forget|tafuta\s+kumbukumbu)\b",
    )),
    ("orchestrator", (
        r"^(?:system\s+(?:health|status|info|telemetry)|system\b.*\b(?:cpu|ram|storage|disk|network|uptime)|(?:cpu|ram|storage|disk|network|uptime)\b)",
        r"^(?:kagua|check|scan|show|onyesha|nipe)\b.*\b(?:afya\s+ya\s+mfumo|system\s+(?:health|status|info)|cpu|ram|storage|disk|network|uptime|hali\s+ya\s+pc)\b",
    )),
    ("jobs", (
        r"^(?:remote\s+jobs?|job\s+search|search\s+jobs?|find\s+jobs?|job\s+research)\b",
        r"^(?:nitafutie|tafutia|tafuta|find(?:\s+me)?|search(?:\s+for)?|research|apply|omba)\b.*\b(?:kazi|ajira|jobs?|employment|position|career|nafasi)\b",
    )),
    ("gmail", (
        r"^(?:email|emails|gmail|inbox|barua\s+pepe)\b",
        r"^(?:soma|read|show|check|angalia|tafuta|search|find|onyesha|nipe|jibu|reply|draft|send|tuma|sambaza|forward)\b.*\b(?:email|emails|mail|gmail|inbox|barua\s+pepe)\b",
    )),
    ("browser", (
        r"^(?:soma\s+ukurasa|read\s+(?:the\s+)?page|show\s+(?:the\s+)?page|angalia\s+ukurasa)\b",
        r"^(?:open|visit|navigate|fungua|nenda|tembelea|click|bonyeza|type|andika|weka|jaza|scroll|sogeza|drag)\b",
    )),
    ("creative", (
        r"^(?:tengeneza|create|make|design|draw|generate|build)\b.*\b(?:bango|poster|banner|graphic|design|logo|flyer|creative)\b",
    )),
    ("device", (
        r"^(?:diagnose|check|kagua|connect|fix|rekebisha|run|fanya|open|fungua)\b.*\b(?:simu|android|adb|fastboot|bluetooth|usb|device|firmware)\b",
        r"^(?:adb|fastboot|bluetooth|device\s+diagnostics)\b",
    )),
    ("security", (
        r"^(?:security\s+scan|security\s+audit|vulnerability\s+scan)\b",
        r"^(?:check|kagua|scan|audit|test|angalia|fanya)\b.*\b(?:security|usalama|vulnerability|malware|port\s+scan)\b",
    )),
    ("coding", (
        r"^(?:chambua|inspect|review|audit|kagua)\b.*\b(?:repo|repository|project|code|msimbo|source|software)\b",
        r"^(?:tengeneza|build|create|make|fix|debug|repair|rekebisha|andika|program|implement|code|review)\b.*\b(?:code|coding|program|repo|github|app|website|tovuti|bug|api|backend|frontend|software)\b",
        r"^(?:fix|debug|repair|rekebisha)\b.*\b(?:bug|error|hitilafu)\b",
    )),
    ("scheduler", (
        r"^(?:schedule|ratiba|remind|kumbusha|set\s+(?:a\s+)?reminder|create\s+(?:a\s+)?schedule)\b",
    )),
    ("research", (
        r"^(?:find|search|research|look\\s+for|tafuta|nitafutie|tafutia|chunguza)\\b.*\\b(?:business\\s+opportunit(?:y|ies)|client\\s+leads?|potential\\s+clients?|customers?|suppliers?|manufacturers?|wholesale|affiliate|referral|prospects?|fursa|wateja|wasambazaji|bidhaa|mapato\\s+mtandaoni)\\b",
        r"^(?:tafuta(?:\s+mtandaoni)?|search(?:\s+(?:the\s+web|online|for))?|research|jua\s+kuhusu|nipe\s+taarifa(?:\s+kuhusu)?|onyesha)\b",
    )),
)


def select_agents(text: str) -> list[str]:
    value = str(text or "").strip().casefold()
    if not value:
        return ["research"]

    # Recognize explicit compound missions such as "Tafuta kazi na soma email".
    # Only command clauses are routed; arbitrary keywords inside a payload are
    # not treated as new work requests.
    clauses = re.split(r"\s+(?:na|kisha|halafu|and\s+then|then)\s+", value)
    selected: list[str] = []
    for clause in clauses:
        for agent_id, patterns in _COMMAND_ROUTES:
            if any(re.search(pattern, clause, flags=re.IGNORECASE) for pattern in patterns):
                if agent_id not in selected:
                    selected.append(agent_id)
                break

    return selected or ["research"]


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
