from __future__ import annotations

from dataclasses import dataclass, field
import re

@dataclass(frozen=True)
class Intent:
    name: str
    confidence: float
    parameters: dict[str, str] = field(default_factory=dict)
    risk: str = "LOW"
    executable: bool = False

_RULES: list[tuple[str, tuple[str, ...], str, str, bool]] = [
    ("SYSTEM_INFO", ("cpu", "ram", "memory", "storage", "disk", "network", "uptime", "system", "hali ya pc"), "LOW", "LOW", True),
    ("MEMORY_SEARCH", ("kumbuka", "remember", "memory", "unakumbuka"), "LOW", "LOW", True),
    ("MEMORY_SAVE", ("hifadhi kumbukumbu", "remember this", "kumbuka hii", "save memory"), "LOW", "LOW", True),
    ("TASK_CREATE", ("tengeneza task", "create task", "ongeza task", "add task", "kazi mpya"), "LOW", "LOW", True),
    ("WEB_RESEARCH", ("tafuta", "search web", "research", "habari za", "jua kuhusu", "web search"), "LOW", "LOW", True),
    ("GMAIL_SEND", ("tuma email", "send email", "send an email", "tuma barua pepe"), "HIGH", "HIGH", False),
    ("GMAIL_SEARCH", ("tafuta email", "search email", "inbox", "barua pepe zangu"), "MEDIUM", "MEDIUM", False),
    ("BROWSER_NAVIGATE", ("fungua website", "open website", "browser", "navigate", "peruzi"), "MEDIUM", "MEDIUM", False),
    ("FILE_DELETE", ("futa file", "delete file", "remove file"), "HIGH", "HIGH", False),
    ("SYSTEM_SHUTDOWN", ("zima computer", "shutdown", "restart computer", "reboot computer"), "HIGH", "HIGH", False),
]

def classify(text: str) -> Intent:
    value = str(text).strip().casefold()
    tokens = set(re.findall(r"[a-zA-ZÀ-ÿ0-9_+-]+", value))
    best: tuple[int, Intent] | None = None
    for name, keywords, _label_risk, risk, executable in _RULES:
        score = 0
        matched = []
        for keyword in keywords:
            if " " in keyword:
                if keyword in value:
                    score += 3
                    matched.append(keyword)
            elif keyword in tokens:
                score += 2
                matched.append(keyword)
        if score:
            confidence = min(0.99, 0.55 + score * 0.08)
            intent = Intent(name=name, confidence=confidence, parameters={"query": value, "matched": ", ".join(matched)}, risk=risk, executable=executable)
            if best is None or score > best[0]:
                best = (score, intent)
    if best:
        return best[1]
    return Intent(name="CHAT", confidence=0.5, parameters={"query": value}, risk="LOW", executable=True)
