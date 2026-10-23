from app.orchestration.planner import build_plan, select_agents


def test_system_health_request_only_selects_orchestrator():
    request = "Kagua afya ya mfumo wa MR AI."

    assert select_agents(request) == ["orchestrator"]

    plan = build_plan(request)
    assert plan["agents"] == ["MR AI Orchestrator"]
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["tools"][-1] == "system_telemetry"


def test_unmatched_request_falls_back_to_research_without_fake_telemetry():
    request = "Nipe muhtasari wa jambo jipya"
    assert select_agents(request) == ["research"]

    plan = build_plan(request)
    assert [step["agent"] for step in plan["steps"]] == ["research"]
    assert all(step["agent"] != "orchestrator" for step in plan["steps"])


def test_gmail_mission_does_not_include_an_unrelated_system_telemetry_step():
    plan = build_plan("Soma email zangu za leo")

    assert [step["agent"] for step in plan["steps"]] == ["gmail"]
