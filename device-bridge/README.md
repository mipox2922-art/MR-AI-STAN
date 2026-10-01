# MR AI STAN — Local Device Bridge

This service runs on the user's own computer, not inside GitHub Codespaces.

It provides a permissioned local bridge for authorized device administration.

## Supported

- Android discovery through ADB
- Android device information
- Android diagnostics and logcat
- Android reboot to system/recovery/bootloader
- Fastboot device discovery
- Explicitly confirmed firmware flashing for supported partitions
- Bluetooth Low Energy discovery through Bleak

## Requirements

- Python 3.11+
- Android SDK Platform Tools (`adb` and `fastboot`) on PATH
- USB debugging enabled and the device authorized for ADB
- Bluetooth hardware for BLE scanning

## Run on Windows

```powershell
cd device-bridge
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:MR_AI_BRIDGE_TOKEN = "generate-a-long-random-token"
$env:MR_AI_WEB_ORIGIN = "https://YOUR-CODESPACE.app.github.dev"
python bridge.py
```

The bridge binds to 127.0.0.1:8765 by default and requires a bearer token for privileged requests.

## Safety

This bridge is for devices you own or are explicitly authorized to administer.
It does not implement lock bypass, credential extraction, FRP bypass, iCloud/activation bypass, or unauthorized access.
Firmware flashing requires explicit confirmation and SHA-256 verification.
