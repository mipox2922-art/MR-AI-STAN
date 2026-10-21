from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import ActivityLog
from app.routers import activity as activity_router


def make_client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(activity_router.router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=4)
    return TestClient(app), factory


def test_audit_event_records_metadata_only():
    client, factory = make_client()
    response = client.post("/activity/events", json={
        "component": "browser", "action": "CLICK", "outcome": "APPROVED",
        "risk": "HIGH", "target_host": "example.com", "request_id": "req-12",
    })
    assert response.status_code == 200
    event = response.json()
    assert event["status"] == "RECORDED"
    with factory() as db:
        row = db.query(ActivityLog).one()
        assert row.user_id == 4
        assert row.action == "SECURITY_ACTION_AUDIT"
        assert "example.com" in row.details
        assert "req-12" in row.details


def test_audit_event_rejects_message_content_and_credentials():
    client, factory = make_client()
    response = client.post("/activity/events", json={
        "component": "browser", "action": "CLICK", "outcome": "APPROVED",
        "risk": "HIGH", "message": "do not log me",
    })
    assert response.status_code == 400
    with factory() as db:
        assert db.query(ActivityLog).count() == 0
