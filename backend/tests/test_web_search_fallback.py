import asyncio

import pytest

from app.config import settings
from app.orchestration.executor import _is_read_only_web_research_request
from app.routers import tools as tools_router


def test_duckduckgo_parser_extracts_only_http_search_results():
    parser = tools_router._DuckDuckGoResultsParser()
    parser.feed("""
        <div class="result">
          <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.org%2Freport"><b>Example</b> Report</a>
          <a class="result__snippet">Public source <b>evidence</b> here</a>
        </div>
        <a class="result__a" href="javascript:alert(1)">Bad link</a>
        <a class="result__a" href="/relative/path">Relative link</a>
    """)

    assert len(parser.results) == 1
    assert parser.results[0]["title"] == "Example Report"
    assert parser.results[0]["url"] == "https://example.org/report"
    assert "Public source" in parser.results[0]["content"]


def test_web_search_uses_free_builtin_fallback_when_searxng_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "searxng_url", "")

    async def fake_search(query):
        return {
            "status": "COMPLETED",
            "query": query,
            "count": 1,
            "results": [{"title": "Verified title", "url": "https://example.org", "content": "Evidence"}],
            "sources": ["DuckDuckGo"],
            "source": "duckduckgo_html",
            "source_warnings": [],
        }

    monkeypatch.setattr(tools_router, "_search_duckduckgo_html", fake_search)
    result = asyncio.run(tools_router._search_searxng("public web research"))

    assert result["status"] == "COMPLETED"
    assert result["source"] == "duckduckgo_html"
    assert result["fallback_used"] is True
    assert result["results"][0]["url"] == "https://example.org"


def test_web_search_falls_back_when_configured_searxng_is_unavailable(monkeypatch):
    import httpx

    monkeypatch.setattr(settings, "searxng_url", "https://searx.example.test")

    class BrokenClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(tools_router.httpx, "AsyncClient", lambda **_kwargs: BrokenClient())

    async def fake_search(query):
        return {
            "status": "COMPLETED",
            "query": query,
            "count": 1,
            "results": [{"title": "Fallback result", "url": "https://example.org", "content": "Public evidence"}],
            "sources": ["DuckDuckGo"],
            "source": "duckduckgo_html",
            "source_warnings": [],
        }

    monkeypatch.setattr(tools_router, "_search_duckduckgo_html", fake_search)
    result = asyncio.run(tools_router._search_searxng("research fallback"))

    assert result["status"] == "COMPLETED"
    assert result["fallback_used"] is True
    assert result["source"] == "duckduckgo_html"
    assert result["source_warnings"] == ["SearXNG: ConnectError"]


def test_web_search_uses_limited_public_api_fallback_when_html_search_has_no_results(monkeypatch):
    monkeypatch.setattr(settings, "searxng_url", "")

    async def empty_duckduckgo(_query):
        return {
            "status": "NO_RESULTS",
            "query": "AI research",
            "results": [],
            "sources": [],
            "source_warnings": [],
        }

    async def public_sources(query, limit=20):
        return {
            "status": "COMPLETED",
            "query": query,
            "count": 1,
            "results": [{"title": "AI overview", "url": "https://en.wikipedia.org/wiki/Artificial_intelligence"}],
            "sources": ["Wikipedia"],
            "source_warnings": [],
            "source_mode": "public_api_fallback",
            "limitations": ["Wikipedia and Hacker News only."],
        }

    monkeypatch.setattr(tools_router, "_search_duckduckgo_html", empty_duckduckgo)
    monkeypatch.setattr(tools_router, "search_public_sources", public_sources)
    result = asyncio.run(tools_router._search_searxng("AI research"))

    assert result["status"] == "COMPLETED"
    assert result["source"] == "public_api_fallback"
    assert result["sources"] == ["Wikipedia"]
    assert result["fallback_used"] is True


@pytest.mark.parametrize(
    "request_text",
    [
        "tafuta mtandaoni AI tools",
        "tafuta kuhusu graphic design clients",
        "search the web for graphic design clients",
        "research public funding opportunities",
        "jua kuhusu remote work",
    ],
)
def test_read_only_web_research_commands_are_allowed(request_text):
    assert _is_read_only_web_research_request(request_text) is True


@pytest.mark.parametrize(
    "request_text",
    [
        "send email to the client",
        "tuma email kwa mteja",
        "apply for remote jobs",
        "submit this form",
        "delete the old files",
        "futa faili za zamani",
        "login to my bank account",
        "password reset",
    ],
)
def test_side_effecting_commands_are_not_autonomous_web_research(request_text):
    assert _is_read_only_web_research_request(request_text) is False
