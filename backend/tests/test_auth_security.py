import os

os.environ["SECRET_KEY"] = "ci-auth-hardening-secret"
os.environ["DATABASE_URL"] = "sqlite:///./ci_auth.db"

from datetime import timedelta

from app.security import create_access_token, decode_access_token


def test_jwt_uses_runtime_configurable_secret():
    token = create_access_token({"sub": "123"}, timedelta(minutes=5))
    payload = decode_access_token(token)
    assert payload["sub"] == "123"


def test_jwt_round_trip_contains_expiry():
    token = create_access_token({"sub": "456"})
    payload = decode_access_token(token)
    assert payload["sub"] == "456"
    assert "exp" in payload
