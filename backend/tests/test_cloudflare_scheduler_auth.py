from fastapi.testclient import TestClient

from app import main
from app.config import settings


def test_cloudflare_scheduler_cycle_requires_secret(monkeypatch):
    secret = "cloudflare-cron-test-secret-that-is-long-enough"
    monkeypatch.setattr(settings, "cloudflare_cron_secret", secret)
    monkeypatch.setattr(settings, "scheduler_enabled", False)

    async def fake_scheduler_cycle():
        return 2, 1

    monkeypatch.setattr(main, "run_scheduler_cycle", fake_scheduler_cycle)

    with TestClient(main.app) as client:
        missing = client.post("/internal/cloudflare/scheduler-cycle")
        assert missing.status_code == 403

        accepted = client.post(
            "/internal/cloudflare/scheduler-cycle",
            headers={"X-MR-AI-Cron-Secret": secret},
        )

    assert accepted.status_code == 200
    assert accepted.json() == {
        "status": "completed",
        "triggered": 2,
        "processed": 1,
    }
