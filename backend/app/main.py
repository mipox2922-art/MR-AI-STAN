import logging

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import Base, engine
from .realtime import manager

from .routers import (
    auth,
    ai,
    memory,
    tasks,
    activity,
    system,
)

logger = logging.getLogger("mr_ai")

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


@app.get("/")
def root():
    return {
        "name": "MR AI",
        "role": "Digital Chief of Staff",
        "status": "ONLINE",
        "architecture": "WEB + EXTENSION + SHARED BACKEND",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)

    except Exception:
        manager.disconnect(websocket)


# ==============================================================================
# GLOBAL EXCEPTION HANDLER
# ==============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
