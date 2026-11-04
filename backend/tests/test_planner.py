from app.orchestration.planner import build_plan, select_agents
from app.tools.router import route_command


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


def test_gmail_mission_does_not_include_unrelated_system_telemetry():
    plan = build_plan("Soma email zangu za leo")
    assert [step["agent"] for step in plan["steps"]] == ["gmail"]


def test_memory_payload_keywords_do_not_launch_unrelated_agents():
    assert select_agents(
        "Kumbuka hii: napenda kazi za graphic design na printing"
    ) == ["memory"]


def test_compound_mission_routes_separate_command_clauses():
    assert select_agents("Tafuta kazi na soma email zangu") == ["jobs", "gmail"]


def test_website_build_routes_to_coding_not_browser_navigation():
    assert select_agents("Tengeneza website") == ["coding"]


def test_direct_mr_ai_fix_commands_route_to_the_coding_agent():
    for request in (
        "Rekebisha MR AI chat",
        "Fix MR AI dashboard",
        "Boresha MR-AI-STAN repo",
    ):
        assert select_agents(request) == ["coding"], request
        assert route_command(request)["tool"] == "coding", request
