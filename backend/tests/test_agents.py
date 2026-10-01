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


from app.orchestration.handoffs import build_browser_handoff


def test_browser_handoff_opens_explicit_url():
    result = build_browser_handoff("fungua https://example.com")
    assert result["action"] == "NAVIGATE"
    assert result["payload"]["url"] == "https://example.com"


def test_browser_handoff_reads_current_page():
    result = build_browser_handoff("soma ukurasa huu")
    assert result["action"] == "GET_PAGE_DATA"


def test_browser_handoff_can_search_web():
    result = build_browser_handoff("tafuta OpenAI Agents")
    assert result["action"] == "NAVIGATE"
    assert "google.com/search?q=" in result["payload"]["url"]
