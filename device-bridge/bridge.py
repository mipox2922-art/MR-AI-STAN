from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

HOST = "127.0.0.1"
PORT = 8765
TOKEN = os.environ.get("MR_AI_BRIDGE_TOKEN", "").strip()
WEB_ORIGIN = os.environ.get("MR_AI_WEB_ORIGIN", "").strip()
ALLOWED_PARTITIONS = {
    "boot", "vendor_boot", "system", "product", "vendor", "recovery", "vbmeta"
}

app = FastAPI(title="MR AI STAN Local Device Bridge", version="0.1.0")

origins = [WEB_ORIGIN] if WEB_ORIGIN else ["http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

def require_token(authorization: str | None = Header(default=None)) -> None:
    if not TOKEN:
        raise HTTPException(503, "MR_AI_BRIDGE_TOKEN is not configured")
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "Invalid bridge token")

def run(cmd: list[str], timeout: int = 20) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Required executable not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "Command timed out: " + " ".join(cmd)) from exc
    output = (result.stdout + chr(10) + result.stderr).strip()
    if result.returncode != 0:
        raise HTTPException(400, output or ("Command failed: " + " ".join(cmd)))
    return output

class RebootRequest(BaseModel):
    mode: Literal["system", "recovery", "bootloader"] = "system"

class FlashRequest(BaseModel):
    serial: str = Field(min_length=1, max_length=128)
    partition: Literal["boot", "vendor_boot", "system", "product", "vendor", "recovery", "vbmeta"]
    image_path: str
    sha256: str = Field(min_length=64, max_length=64)
    confirm: bool = False

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "local_device_bridge",
        "bind": f"{HOST}:{PORT}",
        "adb": bool(shutil.which("adb")),
        "fastboot": bool(shutil.which("fastboot")),
    }

@app.get("/devices/android", dependencies=[Depends(require_token)])
def android_devices():
    raw = run(["adb", "devices", "-l"])
    devices = []
    for line in raw.splitlines():
        if line.startswith("List of devices") or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "state": parts[1], "details": parts[2:]})
    return {"devices": devices}

@app.get("/devices/fastboot", dependencies=[Depends(require_token)])
def fastboot_devices():
    raw = run(["fastboot", "devices"])
    devices = []
    for line in raw.splitlines():
        parts = line.split()
        if parts:
            devices.append({"serial": parts[0], "transport": parts[1] if len(parts) > 1 else ""})
    return {"devices": devices}

@app.get("/devices/{serial}/info", dependencies=[Depends(require_token)])
def android_info(serial: str):
    model = run(["adb", "-s", serial, "shell", "getprop", "ro.product.model"])
    brand = run(["adb", "-s", serial, "shell", "getprop", "ro.product.brand"])
    version = run(["adb", "-s", serial, "shell", "getprop", "ro.build.version.release"])
    sdk = run(["adb", "-s", serial, "shell", "getprop", "ro.build.version.sdk"])
    security_patch = run(["adb", "-s", serial, "shell", "getprop", "ro.build.version.security_patch"])
    return {
        "serial": serial,
        "model": model.strip(),
        "brand": brand.strip(),
        "android_version": version.strip(),
        "sdk": sdk.strip(),
        "security_patch": security_patch.strip(),
    }

@app.get("/devices/{serial}/diagnostics", dependencies=[Depends(require_token)])
def diagnostics(serial: str):
    battery = run(["adb", "-s", serial, "shell", "dumpsys", "battery"])
    storage = run(["adb", "-s", serial, "shell", "df", "-h", "/data"])
    state = run(["adb", "-s", serial, "get-state"])
    return {"serial": serial, "adb_state": state.strip(), "battery": battery, "storage": storage}

@app.get("/devices/{serial}/logs", dependencies=[Depends(require_token)])
def logs(serial: str):
    return {"serial": serial, "logcat": run(["adb", "-s", serial, "logcat", "-d", "-t", "300"], timeout=30)}

@app.post("/devices/{serial}/reboot", dependencies=[Depends(require_token)])
def reboot(serial: str, request: RebootRequest):
    target = {"system": [], "recovery": ["recovery"], "bootloader": ["bootloader"]}[request.mode]
    return {"serial": serial, "mode": request.mode, "result": run(["adb", "-s", serial, "reboot", *target])}

@app.post("/devices/flash", dependencies=[Depends(require_token)])
def flash(request: FlashRequest):
    if not request.confirm:
        raise HTTPException(400, "Explicit confirm=true is required before flashing")
    if request.partition not in ALLOWED_PARTITIONS:
        raise HTTPException(400, "Partition is not permitted by the bridge")
    image = Path(request.image_path).expanduser().resolve()
    if not image.is_file():
        raise HTTPException(404, f"Firmware image not found: {image}")
    digest = hashlib.sha256(image.read_bytes()).hexdigest().lower()
    if digest != request.sha256.lower():
        raise HTTPException(400, "Firmware SHA-256 does not match")
    result = run(["fastboot", "-s", request.serial, "flash", request.partition, str(image)], timeout=300)
    return {
        "serial": request.serial,
        "partition": request.partition,
        "sha256": digest,
        "status": "completed",
        "output": result,
    }

@app.get("/bluetooth/scan", dependencies=[Depends(require_token)])
async def bluetooth_scan():
    try:
        from bleak import BleakScanner
        devices = await BleakScanner.discover(timeout=5.0)
    except Exception as exc:
        raise HTTPException(503, f"Bluetooth scan failed: {type(exc).__name__}: {exc}") from exc
    return {
        "devices": [
            {"name": device.name or "", "address": device.address, "rssi": getattr(device, "rssi", None)}
            for device in devices
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
