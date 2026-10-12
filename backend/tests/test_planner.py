from app.orchestration.planner import build_plan, select_agents


def test_system_health_request_only_selects_orchestrator():
    request = "Kagua afya ya mfumo wa MR AI."

    assert select_agents(request) == ["orchestrator"]

    plan = build_plan(request)
    assert plan["agents"] == ["MR AI Orchestrator"]
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["tools"][-1] == "system_telemetry"


def test_unmatched_request_falls_back_to_research():
    assert select_agents("Nipe muhtasari wa jambo jipya") == [
        "orchestrator",
        "research",
    ]
