from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Risk = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    tools: tuple[str, ...]
    risk: Risk


AGENTS: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        "orchestrator", "MR AI Orchestrator",
        "Plans multi-step work, delegates to specialist agents and tracks verified results.",
        ("planning", "delegation", "verification", "task_tracking"),
        ("agent_router", "mission_planner", "memory"),
        "LOW",
    ),
    AgentDefinition(
        "research", "Research Agent",
        "Collects and summarizes authorized web research and produces source-aware notes.",
        ("web_search", "page_read", "summarize", "source_capture"),
        ("searxng", "browser_hands"),
        "LOW",
    ),
    AgentDefinition(
        "browser", "Browser Agent",
        "Controls an authorized browser session through the MR AI browser extension.",
        ("navigate", "click", "type", "scroll", "extract_visible_text", "download"),
        ("browser_hands",),
        "MEDIUM",
    ),
    AgentDefinition(
        "gmail", "Gmail Agent",
        "Works with mail through approved OAuth/API integrations.",
        ("search_mail", "read_mail", "draft_reply", "create_task"),
        ("gmail",),
        "MEDIUM",
    ),
    AgentDefinition(
        "jobs", "Job Research Agent",
        "Finds remote opportunities, extracts requirements and creates application workflows.",
        ("search_jobs", "deduplicate", "match_profile", "save_jobs", "draft_application"),
        ("searxng", "browser_hands", "memory"),
        "MEDIUM",
    ),
    AgentDefinition(
        "coding", "Coding Agent",
        "Inspects projects, proposes patches, runs tests and prepares code changes.",
        ("inspect_repo", "edit_files", "run_tests", "debug", "commit", "pull_request"),
        ("github",),
        "MEDIUM",
    ),
    AgentDefinition(
        "creative", "Creative Studio Agent",
        "Builds editable poster/banner compositions and exports them to standard formats.",
        ("canvas", "layers", "text", "images", "export_png", "export_jpg", "export_pdf"),
        ("creative_canvas",),
        "LOW",
    ),
    AgentDefinition(
        "device", "Device Lab Agent",
        "Administers authorized devices through the local device bridge.",
        ("adb", "fastboot", "diagnostics", "logs", "reboot", "ble_scan", "firmware_flash"),
        ("device_bridge", "adb", "fastboot"),
        "HIGH",
    ),
    AgentDefinition(
        "security", "Security Agent",
        "Performs defensive security checks and authorized lab diagnostics.",
        ("dependency_audit", "secret_scan", "config_audit", "log_analysis", "port_diagnostics"),
        ("security", "device_bridge"),
        "HIGH",
    ),
    AgentDefinition(
        "memory", "Memory Agent",
        "Stores, retrieves and maintains user-approved memory records.",
        ("remember", "retrieve", "update", "forget"),
        ("memory",),
        "LOW",
    ),
    AgentDefinition(
        "scheduler", "Scheduler Agent",
        "Manages durable tasks and scheduled execution requests.",
        ("schedule", "queue", "cancel", "status"),
        ("scheduler",),
        "MEDIUM",
    ),
)
