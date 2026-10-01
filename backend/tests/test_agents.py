from app.agents.registry import AGENTS
from app.orchestration.planner import build_plan, select_agents


def test_selects_job_agent():
    assert "jobs" in select_agents("nitafutie remote jobs za Python")


def test_selects_device_agent():
    assert "device" in select_agents("chunguza simu kupitia ADB")


def test_build_plan_is_structured():
    result = build_plan("tafuta remote jobs")
    assert result["status"] == "PLANNED"
    assert result["steps"][0]["agent"] == "orchestrator"


def test_every_agent_declares_tools():
    for agent in AGENTS:
        assert agent.tools


def test_job_plan_exposes_real_hands():
    result = build_plan("tafuta remote jobs")
    jobs = next(step for step in result["steps"] if step["agent"] == "jobs")
    assert "searxng" in jobs["tools"]
    assert "browser_hands" in jobs["tools"]


def test_unknown_request_uses_research_fallback():
    assert select_agents("nisaidie kuelewa recursion") == ["orchestrator", "research"]
