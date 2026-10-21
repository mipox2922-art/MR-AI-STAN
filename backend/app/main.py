import logging
import secrets

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings, validate_secret_key
from .github_oidc import verify_github_actions_token
from .database import Base, SessionLocal, engine
from .migrations import run_schema_migrations
from .models import User
from .audit import record_safe_error
from .realtime import manager
from .scheduler import run_scheduler_cycle, start_scheduler, stop_scheduler
from .security import decode_access_token

from .routers import (
    auth,
    ai,
    memory,
    tasks,
    activity,
    system,
    agents,
    tools,
    orchestration,
    integrations,
    jobs,
    scheduler,
    notifications,
)

logger = logging.getLogger("mr_ai")

validate_secret_key(settings.secret_key)

# Serverless Worker imports must not perform database DDL/network I/O.
# Apply schema changes in a controlled migration/setup step instead.
if not settings.serverless_mode:
    Base.metadata.create_all(bind=engine)
    run_schema_migrations(engine)

app = FastAPI(
    title="MR AI — Digital Chief of Staff",
    version="1.0.0-phase1",
)

origins = [
    item.strip()
    for item in settings.cors_origins.split(",")
    if item.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(ai.router)
app.include_router(memory.router)
app.include_router(tasks.router)
app.include_router(activity.router)
app.include_router(system.router)
app.include_router(agents.router)
app.include_router(tools.router)
app.include_router(orchestration.router)
app.include_router(integrations.router)
app.include_router(jobs.router)
app.include_router(scheduler.router)
app.include_router(notifications.router)

# API-prefixed alias for clients and proxies that expose /api/* paths.
app.add_api_route("/api/ai/health", ai.health_check, methods=["GET"], include_in_schema=False)


@app.on_event("startup")
async def startup_scheduler():
    if settings.serverless_mode or not settings.scheduler_enabled:
        return
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_scheduler():
    await stop_scheduler()


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {
        "name": "MR AI",
        "role": "Digital Chief of Staff",
        "status": "ONLINE",
        "architecture": "WEB + EXTENSION + SHARED BACKEND",
    }


@app.get("/health")
async def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check failed because the database is unavailable")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "unavailable"},
        )

    return {
        "status": "healthy",
        "database": "reachable",
        "database_engine": engine.dialect.name,
    }

@app.post("/internal/cloudflare/scheduler-cycle", include_in_schema=False)
async def cloudflare_scheduler_cycle(
    x_mr_ai_cron_secret: str = Header(default=""),
    authorization: str = Header(default=""),
):
    # Keep the legacy shared-secret path for existing trusted callers.
    # GitHub Actions uses a signed OIDC identity token so setup does not depend
    # on copying the same secret into two separate dashboards.
    expected = settings.cloudflare_cron_secret.strip()
    shared_secret_valid = len(expected) >= 32 and secrets.compare_digest(
        x_mr_ai_cron_secret, expected
    )
    if not shared_secret_valid:
        scheme, separator, bearer_token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not bearer_token.strip():
            raise HTTPException(status_code=403, detail="Forbidden")
        await verify_github_actions_token(bearer_token.strip())

    triggered, processed = await run_scheduler_cycle()
    return {
        "status": "completed",
        "triggered": triggered,
        "processed": processed,
    }




@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token", "").strip()
    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        return

    db = SessionLocal()
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
        if not db.query(User).filter(User.id == user_id).first():
            await websocket.close(code=4401, reason="User not found")
            return
    except (TypeError, ValueError, KeyError):
        await websocket.close(code=4401, reason="Invalid authentication token")
        return
    finally:
        db.close()

    await manager.connect(websocket, user_id)

    try:
        await websocket.send_json({
            "event": "CONNECTED",
            "data": {"user_id": user_id},
        })
        while True:
            message = await websocket.receive_text()
            if message.strip().casefold() in {"ping", "heartbeat"}:
                await websocket.send_json({"event": "PONG", "data": {}})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Associate the record with the authenticated user when possible, but never
    # store Authorization headers, request bodies, prompts, or raw exceptions.
    user_id = None
    try:
        scheme, separator, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer" and separator and token.strip():
            claims = decode_access_token(token.strip())
            user_id = int(claims.get("sub"))
    except Exception:
        user_id = None

    db = SessionLocal()
    try:
        record_safe_error(
            db,
            user_id,
            component=request.url.path,
            code=type(exc).__name__,
            message_safe="Unhandled server error; request payload omitted from log.",
        )
    except Exception:
        # Safe logging is best effort and must never hide the original HTTP failure.
        pass
    finally:
        db.close()

    logger.error("Unhandled error on route=%s error_type=%s", request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
