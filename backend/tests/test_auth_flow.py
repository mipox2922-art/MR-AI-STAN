from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import User
from app.routers.auth import router


def build_client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth_flow.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_factory


def test_auth_status_requires_setup_for_empty_database(tmp_path):
    client, _ = build_client(tmp_path)

    response = client.get("/auth/status")

    assert response.status_code == 200
    assert response.json() == {"setup_required": True}


def test_register_then_login_round_trip(tmp_path):
    client, session_factory = build_client(tmp_path)

    register_response = client.post(
        "/auth/register",
        json={"username": "operator", "password": "StrongPass123!"},
    )

    assert register_response.status_code == 200
    assert register_response.json()["token_type"] == "bearer"
    assert register_response.json()["access_token"]

    login_response = client.post(
        "/auth/login",
        json={"username": "operator", "password": "StrongPass123!"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["token_type"] == "bearer"
    assert login_response.json()["access_token"]

    with session_factory() as db:
        user = db.query(User).filter(User.username == "operator").first()
        assert user is not None


def test_login_rejects_wrong_password_without_leaking_user_state(tmp_path):
    client, _ = build_client(tmp_path)

    client.post(
        "/auth/register",
        json={"username": "operator", "password": "StrongPass123!"},
    )

    response = client.post(
        "/auth/login",
        json={"username": "operator", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"
