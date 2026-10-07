from app.orchestration.handoffs import build_browser_handoff


def test_browser_handoff_reads_page():
    result = build_browser_handoff("soma ukurasa")
    assert result["action"] == "GET_PAGE_DATA"
    assert result["payload"] == {}


def test_browser_handoff_parses_safe_click():
    result = build_browser_handoff("bonyeza #next-button")
    assert result["action"] == "CLICK"
    assert result["payload"]["selector"] == "#next-button"


def test_browser_handoff_parses_type():
    result = build_browser_handoff("andika #search: artificial intelligence")
    assert result["action"] == "TYPE"
    assert result["payload"] == {
        "selector": "#search",
        "value": "artificial intelligence",
    }


def test_browser_handoff_parses_scroll_direction():
    result = build_browser_handoff("scroll juu 500")
    assert result["action"] == "SCROLL"
    assert result["payload"]["amount"] == -500


def test_browser_handoff_parses_drag():
    result = build_browser_handoff("drag #card 120 -40")
    assert result["action"] == "DRAG"
    assert result["payload"] == {
        "selector": "#card",
        "dx": 120,
        "dy": -40,
    }


def test_browser_handoff_blocks_consequential_click_language():
    assert build_browser_handoff("bonyeza #submit") is None


def test_browser_handoff_rejects_unsupported_click_target_text():
    assert build_browser_handoff("bonyeza submit button") is None
