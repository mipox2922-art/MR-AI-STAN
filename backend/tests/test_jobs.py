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



def test_job_tracking_does_not_claim_independent_verification_for_supplied_link():
    from app.routers.jobs import _build_tracking_record

    tracking = _build_tracking_record(
        status="APPLIED",
        evidence_url="https://example.com/application/123",
        previous={},
        owner_confirmed=True,
    )

    assert tracking["status"] == "APPLIED"
    assert tracking["verified"] is False
    assert tracking["owner_confirmed"] is True
    assert tracking["evidence_status"] == "PROVIDED_NOT_CHECKED"
    assert "not been independently checked" in tracking["truth_note"]


def test_job_tracking_preserves_existing_link_without_claiming_it_was_checked():
    from app.routers.jobs import _build_tracking_record

    tracking = _build_tracking_record(
        status="INTERVIEW",
        evidence_url="",
        previous={"evidence_url": "https://example.com/interview"},
        owner_confirmed=True,
    )

    assert tracking["evidence_url"] == "https://example.com/interview"
    assert tracking["evidence_status"] == "PROVIDED_NOT_CHECKED"
    assert tracking["verified"] is False
