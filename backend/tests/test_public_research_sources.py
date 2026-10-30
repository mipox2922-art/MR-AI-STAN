import asyncio

import httpx

from app.research import public_sources


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses):
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, **_kwargs):
        if "wikipedia.org" in url:
            value = self.responses.get("wikipedia")
        else:
            value = self.responses.get("hacker_news")
        if isinstance(value, Exception):
            raise value
        return FakeResponse(value or {})


def test_public_research_combines_real_source_records_and_links(monkeypatch):
    monkeypatch.setattr(
        public_sources.httpx,
        "AsyncClient",
        lambda **_kwargs: FakeClient({
            "wikipedia": {"query": {"search": [{
                "title": "Graphic design",
                "snippet": "Graphic design is a creative discipline.",
            }]}},
            "hacker_news": {"hits": [{
                "title": "Design tools for independent creators",
                "url": "https://news.example.test/design-tools",
                "story_text": "A source story about creator tools.",
                "created_at": "2026-10-30T10:00:00Z",
                "points": 42,
                "objectID": "123",
            }]},
        }),
    )

    result = asyncio.run(public_sources.search_public_sources("graphic design", limit=10))

    assert result["status"] == "COMPLETED"
    assert result["count"] == 2
    assert set(result["sources"]) == {"Wikipedia", "Hacker News"}
    assert all(item["url"].startswith("https://") for item in result["results"])
    assert all(item["source"] for item in result["results"])
    assert result["source_mode"] == "public_api_fallback"


def test_public_research_keeps_partial_results_when_one_source_fails(monkeypatch):
    monkeypatch.setattr(
        public_sources.httpx,
        "AsyncClient",
        lambda **_kwargs: FakeClient({
            "wikipedia": httpx.ConnectError("temporary source outage"),
            "hacker_news": {"hits": [{
                "title": "A technology research item",
                "url": "https://news.example.test/story",
                "objectID": "321",
            }]},
        }),
    )

    result = asyncio.run(public_sources.search_public_sources("AI tools", limit=5))

    assert result["status"] == "COMPLETED"
    assert result["count"] == 1
    assert result["sources"] == ["Hacker News"]
    assert any(item.startswith("Wikipedia:") for item in result["source_warnings"])


def test_public_research_reports_source_error_when_every_source_fails(monkeypatch):
    monkeypatch.setattr(
        public_sources.httpx,
        "AsyncClient",
        lambda **_kwargs: FakeClient({
            "wikipedia": httpx.ConnectError("down"),
            "hacker_news": httpx.ConnectError("down"),
        }),
    )

    result = asyncio.run(public_sources.search_public_sources("research topic"))

    assert result["status"] == "SOURCE_ERROR"
    assert result["results"] == []
    assert len(result["source_warnings"]) == 2


def test_empty_public_research_query_is_rejected_without_network(monkeypatch):
    def should_not_create_client(**_kwargs):
        raise AssertionError("An empty query must not make a network request.")

    monkeypatch.setattr(public_sources.httpx, "AsyncClient", should_not_create_client)
    result = asyncio.run(public_sources.search_public_sources("   "))
    assert result["status"] == "REJECTED"
    assert result["results"] == []
