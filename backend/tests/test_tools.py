from app.tools.router import route_command

def test_routes_system_to_telemetry():
    result = route_command("kaka angalia CPU na RAM za mfumo")
    assert result["tool"] == "system_telemetry"
    assert result["execution"] == "BACKEND"

def test_routes_research_to_search():
    result = route_command("tafuta habari za AI leo")
    assert result["tool"] == "searxng"

def test_routes_browser_command_to_browser_hands():
    result = route_command("fungua browser na bonyeza")
    assert result["tool"] == "browser_hands"

def test_routes_android_to_device_bridge():
    result = route_command("chunguza simu kupitia ADB")
    assert result["tool"] == "device_bridge"
    assert result["risk"] == "HIGH"

def test_no_tool_match_keeps_ai_only():
    result = route_command("nisaidie kuelewa recursion")
    assert result["status"] == "NO_TOOL_MATCH"
    assert result["execution"] == "AI_ONLY"
