from __future__ import annotations

import os
from urllib.parse import quote

import asgi
from workers import WorkerEntrypoint


_app = None


def _hyperdrive_database_url(hyperdrive) -> str:
    user = quote(str(hyperdrive.user), safe="")
    password = quote(str(hyperdrive.password), safe="")
    host = str(hyperdrive.host)
    port = int(hyperdrive.port)
    database = quote(str(hyperdrive.database), safe="")
    return (
        f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"
        "?sslmode=require"
    )


def _configure_runtime(env) -> None:
    os.environ["DATABASE_URL"] = _hyperdrive_database_url(env.HYPERDRIVE)
    os.environ["SECRET_KEY"] = str(env.SECRET_KEY)
    os.environ["CORS_ORIGINS"] = str(
        getattr(env, "CORS_ORIGINS", "https://mr-ai-stan.pages.dev")
    )
    os.environ["SERVERLESS_MODE"] = "true"

    optional_keys = (
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GEMINI_TIER",
        "KIMI_API_KEY",
        "KIMI_MODEL",
        "KIMI_BASE_URL",
        "SEARXNG_URL",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "GMAIL_REDIRECT_URI",
        "GMAIL_SCOPES",
    )
    for key in optional_keys:
        value = getattr(env, key, None)
        if value is not None:
            os.environ[key] = str(value)


def _get_app(env):
    global _app
    if _app is None:
        _configure_runtime(env)
        from app.main import app

        _app = app
    return _app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(_get_app(self.env), request, self.env)

    async def scheduled(self, controller, env, ctx):
        _get_app(env)
        from app.scheduler import run_scheduler_cycle

        await run_scheduler_cycle()
