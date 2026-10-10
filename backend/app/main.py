import logging

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings, validate_secret_key
from .database import Base, SessionLocal, engine
from .models import User
from .realtime import manager
from .scheduler import start_scheduler, stop_scheduler
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
    scheduler,
    notifications,
)

logger = logging.getLogger("mr_ai")

validate_secret_key(settings.secret_key)

# Serverless Worker imports must not perform database DDL/network I/O.
# Apply schema changes in a controlled migration/setup step instead.
if not settings.serverless_mode:
    Base.metadata.create_all(bind=engine)

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
app.include_router(scheduler.router)
app.include_router(notifications.router)


@app.on_event("startup")
async def startup_scheduler():
    if settings.serverless_mode or not settings.scheduler_enabled:
        return
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_scheduler():
    await stop_scheduler()


@app.get("/")
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

    return {"status": "healthy", "database": "reachable"}


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
    logger.exception("Unhandled error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
