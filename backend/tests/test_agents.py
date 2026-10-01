from app.orchestration.planner import build_plan, select_agents


def test_selects_job_agent():
    assert "jobs" in select_agents("nitafutie remote jobs za Python")


def test_selects_device_agent():
    assert "device" in select_agents("chunguza simu kupitia ADB")


def test_build_plan_is_structured():
    result = build_plan("tafuta remote jobs")
    assert result["status"] == "PLANNED"
    assert result["steps"][0]["agent"] == "orchestrator"
