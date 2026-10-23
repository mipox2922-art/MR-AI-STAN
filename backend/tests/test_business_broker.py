import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import BusinessOpportunity, Task
from app.routers import business_broker


def build_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    actor = [SimpleNamespace(id=101)]

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(business_broker.router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: actor[0]
    return TestClient(app), factory, actor


def test_research_persists_source_and_builds_draft_follow_up(monkeypatch):
    client, factory, _actor = build_client()

    async def fake_sources(goal, opportunity_type, limit):
        assert "graphic design" in goal.casefold()
        assert opportunity_type == "CLIENT_LEAD"
        assert limit == 5
        return {
            "status": "COMPLETED",
            "query": "test source query",
            "source_names": ["Test Search"],
            "source_warnings": [],
            "items": [{
                "title": "Graphic design support requested",
                "organization": "Example Studio",
                "summary": "Public source text that describes a potential need for design services and gives enough context for an owner to review it.",
                "source_name": "Test Search",
                "source_url": "https://example.test/opportunity/design",
                "evidence": {"record_id": "test-1", "listing_date": "2026-10-23"},
            }],
        }

    monkeypatch.setattr(business_broker, "_fetch_broker_sources", fake_sources)
    response = client.post("/broker/research", json={
        "goal": "Find businesses that need graphic design",
        "opportunity_type": "CLIENT_LEAD",
        "max_results": 5,
        "prepare_workflow": True,
        "offer": "graphic design and branding",
    })

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["saved_count"] == 1
    assert payload["new_count"] == 1
    opportunity = payload["opportunities"][0]
    assert opportunity["source_url"] == "https://example.test/opportunity/design"
    assert opportunity["source_checked_at"]
    assert opportunity["evidence"]["identity_verified"] is False
    assert opportunity["fit_score"] > 0
    assert opportunity["status"] == "CONTACT_DRAFTED"
    assert "graphic design and branding" in opportunity["outreach_body"]
    assert payload["workflow"][0]["message_sent"] is False
    assert payload["workflow"][0]["follow_up_task_id"]

    with factory() as db:
        stored = db.query(BusinessOpportunity).filter_by(id=opportunity["id"], user_id=101).one()
        task = db.query(Task).filter_by(
            user_id=101,
            source="business_broker",
            requested_by=f"business_broker:opportunity:{stored.id}",
        ).one()
        assert stored.follow_up_task_id == task.id
        assert task.deadline is not None
        assert task.status == "PENDING"
        assert json.loads(task.description)["outreach_is_draft_only"] is True


def test_remote_work_broker_uses_existing_public_job_feed(monkeypatch):
    client, _factory, _actor = build_client()
    import app.routers.jobs as jobs_module

    async def fake_jobs(query, limit=25):
        assert query == "graphic design"
        assert limit == 4
        return {
            "status": "COMPLETED",
            "query": query,
            "count": 1,
            "sources": ["Remotive"],
            "source_warnings": [],
            "results": [{
                "id": "public-job-42",
                "title": "Graphic Designer",
                "company": "Example Remote Employer",
                "location": "Worldwide",
                "url": "https://example.test/jobs/42",
                "description": "An illustrative test record, not a real vacancy.",
                "tags": ["design"],
                "published_at": "2026-10-23",
                "source": "Remotive",
            }],
            "note": "Test fixture only.",
        }

    monkeypatch.setattr(jobs_module, "research_public_jobs", fake_jobs)
    response = client.post("/broker/research", json={
        "goal": "Find remote graphic design jobs",
        "opportunity_type": "REMOTE_WORK",
        "max_results": 4,
        "prepare_workflow": True,
    })

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["saved_count"] == 1
    item = payload["opportunities"][0]
    assert item["source_name"] == "Remotive"
    assert item["evidence"]["identity_verified"] is False
    assert item["outreach_subject"].startswith("Question about opportunity")
    assert payload["workflow"][0]["message_sent"] is False


def test_missing_search_connector_returns_not_connected_without_fake_records(monkeypatch):
    client, factory, _actor = build_client()
    monkeypatch.setattr(settings, "searxng_url", "")

    response = client.post("/broker/research", json={
        "goal": "Find suppliers of printing materials",
        "opportunity_type": "SUPPLIER",
    })

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "NOT_CONNECTED"
    assert payload["saved_count"] == 0
    assert payload["opportunities"] == []
    with factory() as db:
        assert db.query(BusinessOpportunity).count() == 0


def test_missing_cost_inputs_are_unknown_not_zero_and_manual_record_is_unverified():
    client, _factory, _actor = build_client()
    response = client.post("/broker/opportunities", json={
        "title": "Example product sourcing lead",
        "opportunity_type": "PRODUCT",
        "summary": "Owner-submitted source needing verification.",
        "source_name": "Owner submitted",
        "source_url": "https://example.test/product",
        "currency": "USD",
        "selling_price": 100,
        "supplier_cost": 40,
    })

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "UNVERIFIED"
    assert payload["risk_level"] == "HIGH"
    assert payload["gross_margin_amount"] == 60.0
    assert payload["gross_margin_percent"] == 60.0
    assert payload["net_margin_amount"] is None
    assert payload["shipping_cost"] is None
    assert payload["fees_taxes"] is None
    assert payload["evidence"]["identity_verified"] is False


def test_opportunity_records_are_isolated_per_owner():
    client, _factory, actor = build_client()
    created = client.post("/broker/opportunities", json={
        "title": "Test supplier",
        "opportunity_type": "SUPPLIER",
        "summary": "Must remain in its owner's pipeline.",
        "source_name": "Owner submitted",
        "source_url": "https://example.test/supplier",
    })
    assert created.status_code == 200, created.text
    opportunity_id = created.json()["id"]

    actor[0] = SimpleNamespace(id=202)
    response = client.get(f"/broker/opportunities/{opportunity_id}")
    assert response.status_code == 404
    assert client.get("/broker/opportunities").json() == []


def test_manual_opportunity_rejects_non_https_source():
    client, _factory, _actor = build_client()
    response = client.post("/broker/opportunities", json={
        "title": "Suspicious link",
        "opportunity_type": "SUPPLIER",
        "source_name": "Manual",
        "source_url": "http://example.test/supplier",
    })
    assert response.status_code == 422
