from app.routers.jobs import _clean_job


def test_clean_job_normalizes_remoteok_posting():
    result = _clean_job(
        {
            "id": "123",
            "position": "Python Engineer",
            "company": "Example Co",
            "url": "https://example.com/jobs/123",
            "location": "Worldwide",
            "tags": ["python", "backend"],
            "description": "Build APIs",
        },
        "RemoteOK",
    )
    assert result is not None
    assert result["title"] == "Python Engineer"
    assert result["company"] == "Example Co"
    assert result["source"] == "RemoteOK"
    assert result["tags"] == ["python", "backend"]


def test_clean_job_rejects_missing_title_and_non_https_url():
    assert _clean_job({"company": "Example", "url": "https://example.com"}, "test") is None
    assert _clean_job({"title": "Bad URL", "url": "http://example.com"}, "test") is None
