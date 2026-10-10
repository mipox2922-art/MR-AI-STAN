import os

os.environ["SECRET_KEY"] = "ci-only-secret-for-auth-security-tests-2026"
os.environ["DATABASE_URL"] = "sqlite:///./ci_auth.db"

from datetime import timedelta

import pytest

from app.config import validate_secret_key
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



def test_secret_key_validation_rejects_default_and_short_values():
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        validate_secret_key("short")

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        validate_secret_key("CHANGE_THIS_SECRET_KEY")


def test_secret_key_validation_accepts_long_random_value():
    validate_secret_key("a-random-test-key-that-is-at-least-32-characters-long")
