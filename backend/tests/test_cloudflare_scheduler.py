import asyncio

import pytest
from fastapi import HTTPException

from app import main


def test_cloudflare_scheduler_cycle_rejects_invalid_internal_secret(monkeypatch):
    monkeypatch.setattr(main.settings, "cloudflare_cron_secret", "configured-secret-value-longer-than-32-chars")

    with pytest.raises(HTTPException) as error:
        asyncio.run(main.cloudflare_scheduler_cycle("wrong-secret"))

    assert error.value.status_code == 403


def test_cloudflare_scheduler_cycle_runs_with_valid_internal_secret(monkeypatch):
    secret = "a-random-cron-secret-that-is-longer-than-32-characters"
    monkeypatch.setattr(main.settings, "cloudflare_cron_secret", secret)

    async def fake_cycle():
        return 2, 3

    monkeypatch.setattr(main, "run_scheduler_cycle", fake_cycle)

    response = asyncio.run(main.cloudflare_scheduler_cycle(secret))

    assert response == {
        "status": "completed",
        "triggered": 2,
        "processed": 3,
    }
