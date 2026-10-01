from app.tools.registry import get_tool_registry, registry_summary

def test_tool_registry_has_free_core_tools():
    tools = get_tool_registry()
    ids = {tool["id"] for tool in tools}
    assert {"browser_hands", "device_bridge", "openstreetmap", "creative_canvas", "searxng"} <= ids

def test_tool_registry_does_not_fake_optional_tools():
    tools = get_tool_registry()
    playwright = next(tool for tool in tools if tool["id"] == "playwright")
    assert playwright["status"].startswith("OPTIONAL")
    assert registry_summary()["total"] == len(tools)
