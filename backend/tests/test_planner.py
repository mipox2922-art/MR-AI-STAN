from app.orchestration.planner import build_plan, has_explicit_agent_route, select_agents
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
        "Kagua MR AI dashboard",
        "Angalia MR AI chat",
        "Ongeza feature kwenye MR AI chat",
        "Refactor MR AI dashboard",
    ):
        assert select_agents(request) == ["coding"], request
        assert route_command(request)["tool"] == "coding", request



def test_explicit_commands_keep_each_agent_inside_its_own_clause():
    request = "Tafuta kazi za remote designer na soma email zangu"

    plan = build_plan(request)

    assert [step["agent"] for step in plan["steps"]] == ["jobs", "gmail"]
    assert plan["steps"][0]["request"] == "Tafuta kazi za remote designer"
    assert plan["steps"][1]["request"] == "soma email zangu"
    assert has_explicit_agent_route("Tengeneza website")
    assert has_explicit_agent_route("Kagua MR AI dashboard")
    assert not has_explicit_agent_route("Habari kaka, unaendeleaje?")



def test_same_agent_actions_remain_separate_so_unsupported_side_effects_are_not_hidden():
    plan = build_plan("Find jobs and apply")

    assert [step["agent"] for step in plan["steps"]] == ["jobs", "jobs"]
    assert [step["request"] for step in plan["steps"]] == ["Find jobs", "apply"]
    assert select_agents("Find jobs and apply") == ["jobs"]



def test_descriptive_tail_after_agent_command_is_not_dropped():
    plan = build_plan("Create logo and banner")

    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["agent"] == "creative"
    assert plan["steps"][0]["request"] == "Create logo na banner"



def test_natural_language_goal_is_delegated_without_naming_agents():
    from app.orchestration.planner import has_autonomous_goal, has_multiple_agent_routes

    request = "I need you to find remote jobs and check my Gmail inbox"

    assert has_autonomous_goal(request)
    assert has_multiple_agent_routes(request)
    assert select_agents(request) == ["jobs", "gmail"]


def test_broad_owner_goal_assigns_research_and_jobs_specialists():
    request = "I need more clients and remote job opportunities"

    assert select_agents(request) == ["jobs", "research"]
    plan = build_plan(request)
    assert [step["agent"] for step in plan["steps"]] == ["jobs", "research"]
    assert all(step["request"] for step in plan["steps"])


def test_explanatory_question_does_not_start_agent_work():
    from app.orchestration.planner import has_autonomous_goal

    assert not has_autonomous_goal("Can you explain remote jobs?")
    assert not has_autonomous_goal("Nielezee kuhusu email automation")


def test_manager_plan_uses_free_ai_and_validates_agent_assignments(monkeypatch):
    import asyncio
    import json
    import app.routers.ai as ai_module
    import app.routers.system as system_module
    from app.orchestration.planner import build_autonomous_plan

    monkeypatch.setattr(system_module, "_default_ai_provider", lambda: ("openrouter", "openrouter/free", "OPENROUTER_FREE"))
    calls = {}

    async def fake_reply(provider, prompt, timeout=85):
        calls.update(provider=provider, prompt=prompt, timeout=timeout)
        return json.dumps({
            "goal": "Find employment and clients",
            "steps": [
                {"agent": "jobs", "request": "Search remote jobs matching the owner's skills"},
                {"agent": "research", "request": "Find prospective clients for MOOG Digital"},
                {"agent": "unknown-agent", "request": "Do unrelated work"},
            ],
        }), "openrouter"

    monkeypatch.setattr(ai_module, "generate_reply_with_fallback", fake_reply)
    plan = asyncio.run(build_autonomous_plan("I need more clients and remote job opportunities"))

    assert calls["provider"] == "openrouter"
    assert calls["timeout"] == 18
    assert plan["planner"] == "free_ai_manager:openrouter"
    assert [step["agent"] for step in plan["steps"]] == ["jobs", "research"]
    assert all(step["status"] == "PLANNED" for step in plan["steps"])


def test_manager_plan_falls_back_to_deterministic_routing_when_free_provider_missing(monkeypatch):
    import asyncio
    import app.routers.system as system_module
    from app.orchestration.planner import build_autonomous_plan

    monkeypatch.setattr(system_module, "_default_ai_provider", lambda: (None, None, None))
    plan = asyncio.run(build_autonomous_plan("I need more clients and remote job opportunities"))

    assert plan["planner"] == "deterministic_goal_routing"
    assert [step["agent"] for step in plan["steps"]] == ["jobs", "research"]



def test_owner_can_describe_autonomous_agent_goal_naturally_in_swahili():
    request = (
        "Sasa naitaji MR AI aweze kuji tuma mwenyewe majukumu, "
        "ana timu ya agent na mimi napitia alichofanya"
    )
    assert select_agents(request) == ["coding"]


def test_343shop_goals_are_routed_to_the_shop_specialist():
    from app.orchestration.planner import infer_goal_commands, select_agents

    request = "Kagua 343Shop bidhaa na oda mpya"
    assert "shop" in select_agents(request)
    commands = infer_goal_commands(request)
    shop_step = next(item for item in commands if item["agent"] == "shop")
    assert "343Shop" in shop_step["request"]
    assert "do not change prices" in shop_step["request"]


def test_owner_wide_goal_delegates_known_owner_workstreams_without_agent_names():
    from app.orchestration.planner import infer_goal_commands, select_agents

    request = "Simamia shughuli zangu zote"
    selected = select_agents(request)
    assert selected == ["jobs", "gmail", "research", "shop", "coding"]
    plan = infer_goal_commands(request)
    assert len(plan) == 5
    assert all(item["request"] for item in plan)
