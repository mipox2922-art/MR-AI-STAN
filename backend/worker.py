from __future__ import annotations

import os
import traceback
from urllib.parse import urlsplit

from workers import Response, WorkerEntrypoint, asgi


_app = None


def _configure_runtime(env) -> None:
    os.environ["DATABASE_URL"] = str(env.DATABASE_URL)
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
        try:
            return await asgi.fetch(_get_app(self.env), request.js_object, self.env)
        except Exception as exc:
            # Keep diagnostic detail in Worker logs, never expose exception text or secrets.
            print("MR_AI_WORKER_FETCH_EXCEPTION", type(exc).__module__, type(exc).__name__)
            traceback.print_exc()
            request_path = urlsplit(str(request.url)).path
            if request_path == "/health":
                return Response(
                    content=f"MR AI Worker internal failure: {type(exc).__name__}",
                    status=500,
                    headers={"content-type": "text/plain; charset=utf-8"},
                )
            raise

    async def scheduled(self, controller, env, ctx):
        _get_app(env)
        from app.scheduler import run_scheduler_cycle

        await run_scheduler_cycle()
