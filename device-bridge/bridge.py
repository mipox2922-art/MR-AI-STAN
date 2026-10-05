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


def _wifi_scan_windows() -> list[dict]:
    result = run(["netsh", "wlan", "show", "networks", "mode=bssid"], timeout=15)
    networks = []
    current = None
    for raw_line in result.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.casefold()
        if lower.startswith("ssid ") and ":" in line and "BSSID" not in line:
            ssid = line.split(":", 1)[1].strip()
            current = {"ssid": ssid, "bssids": []}
            networks.append(current)
            continue
        if current and lower.startswith("bssid ") and ":" in line:
            bssid = line.split(":", 1)[1].strip()
            current["bssids"].append({"bssid": bssid})
            continue
        if current and current["bssids"] and ":" in line:
            key, value = [part.strip() for part in line.split(":", 1)]
            item = current["bssids"][-1]
            key_lower = key.casefold()
            if key_lower == "signal":
                item["signal"] = value
            elif key_lower == "channel":
                item["channel"] = value
            elif key_lower == "radio type":
                item["radio_type"] = value
            elif key_lower == "authentication":
                item["authentication"] = value
    return networks


def _wifi_scan_linux() -> list[dict]:
    result = run([
        "nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,CHAN,SECURITY",
        "dev", "wifi", "list", "--rescan", "yes"
    ], timeout=20)
    networks = []
    for line in result.splitlines():
        parts = line.split(":")
        if len(parts) < 5:
            continue
        networks.append({
            "ssid": parts[0],
            "bssid": parts[1],
            "signal_percent": parts[2],
            "channel": parts[3],
            "security": ":".join(parts[4:]),
        })
    return networks

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


@app.get("/devices/{serial}/boot-state", dependencies=[Depends(require_token)])
def boot_state(serial: str):
    props = {}
    for key in (
        "ro.boot.flash.locked",
        "ro.boot.vbmeta.device_state",
        "ro.boot.verifiedbootstate",
        "ro.boot.veritymode",
    ):
        value = run(["adb", "-s", serial, "shell", "getprop", key]).strip()
        props[key] = value
    return {
        "serial": serial,
        "state": props,
        "note": "These are boot/security state signals only; they do not bypass device protection.",
    }


@app.get("/location/public", dependencies=[Depends(require_token)])
def public_location():
    try:
        from urllib.request import Request, urlopen
        request = Request(
            "https://ipwho.is/",
            headers={"User-Agent": "MR-AI-STAN-Local-Bridge/0.1"},
        )
        with urlopen(request, timeout=8) as response:
            import json
            data = json.load(response)
    except Exception as exc:
        raise HTTPException(503, f"Public IP geolocation unavailable: {type(exc).__name__}: {exc}") from exc

    if data.get("success") is False:
        raise HTTPException(503, "Public IP geolocation provider rejected the request")

    return {
        "source": "ipwho.is",
        "ip": data.get("ip"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "city": data.get("city"),
        "region": data.get("region"),
        "country": data.get("country"),
        "country_code": data.get("country_code"),
        "timezone": (data.get("timezone") or {}).get("id"),
        "note": "IP location is approximate and may reflect a VPN, proxy, ISP gateway, or mobile carrier.",
    }

@app.get("/radio/status", dependencies=[Depends(require_token)])
def radio_status():
    rtl_power = shutil.which("rtl_power")
    rtl_test = shutil.which("rtl_test")
    return {
        "receive_only": True,
        "rtl_power_available": bool(rtl_power),
        "rtl_test_available": bool(rtl_test),
        "status": "READY" if rtl_power or rtl_test else "NO_SDR_TOOL",
        "note": "A software dashboard cannot detect arbitrary radio spectrum without compatible RF hardware.",
    }

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



@app.get("/radar/scan", dependencies=[Depends(require_token)])
async def radar_scan():
    findings = []

    try:
        wifi = wifi_scan()
        for network in wifi.get("networks", []):
            ssid = network.get("ssid") or "(hidden)"
            signal = network.get("signal_percent") or (
                network.get("bssids", [{}])[0].get("signal") if network.get("bssids") else None
            )
            findings.append({
                "type": "wifi",
                "label": ssid,
                "signal": signal,
                "source": wifi.get("source"),
            })
    except HTTPException as exc:
        wifi = {"status": "UNAVAILABLE", "reason": exc.detail}

    try:
        bluetooth = await bluetooth_scan()
        for device in bluetooth.get("devices", []):
            findings.append({
                "type": "bluetooth",
                "label": device.get("name") or device.get("address") or "BLE device",
                "signal": device.get("rssi"),
                "source": "BLE",
            })
    except HTTPException:
        bluetooth = {"status": "UNAVAILABLE"}

    try:
        android = android_devices()
    except HTTPException:
        android = {"devices": []}

    for device in android.get("devices", []):
        findings.append({
            "type": "android",
            "label": device.get("serial", "Android"),
            "signal": None,
            "source": "ADB",
        })

    try:
        fastboot = fastboot_devices()
    except HTTPException:
        fastboot = {"devices": []}

    for device in fastboot.get("devices", []):
        findings.append({
            "type": "fastboot",
            "label": device.get("serial", "Fastboot"),
            "signal": None,
            "source": "FASTBOOT",
        })

    radio = radio_status()
    return {
        "status": "READY",
        "findings": findings,
        "counts": {
            "total": len(findings),
            "wifi": sum(item["type"] == "wifi" for item in findings),
            "bluetooth": sum(item["type"] == "bluetooth" for item in findings),
            "android": sum(item["type"] == "android" for item in findings),
            "fastboot": sum(item["type"] == "fastboot" for item in findings),
        },
        "radio": radio,
        "note": "Local receive/diagnostic sensors only. No arbitrary radio-spectrum data is claimed without SDR hardware.",
    }

@app.get("/wifi/scan", dependencies=[Depends(require_token)])
def wifi_scan():
    if os.name == "nt" and shutil.which("netsh"):
        return {"platform": "windows", "networks": _wifi_scan_windows(), "source": "netsh wlan"}
    if shutil.which("nmcli"):
        return {"platform": "linux", "networks": _wifi_scan_linux(), "source": "nmcli"}
    raise HTTPException(503, "No supported local Wi-Fi scanner found")

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
