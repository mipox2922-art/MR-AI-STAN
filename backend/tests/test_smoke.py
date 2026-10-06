import os

os.environ["SECRET_KEY"] = "ci-smoke-test-secret"
os.environ["DATABASE_URL"] = "sqlite:///./ci_smoke.db"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_register_and_login():
    username = "ci_smoke_user"
    password = "ci_smoke_password"

    register = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )

    assert register.status_code == 200
    token = register.json()["access_token"]
    assert token
    assert register.json()["token_type"] == "bearer"

    login = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )

    assert login.status_code == 200
    assert login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"


def test_invalid_login_is_rejected():
    response = client.post(
        "/auth/login",
        json={
            "username": "ci_missing_user",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
