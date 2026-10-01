# MR AI STAN — Digital Chief of Staff

Project ID: MR-AI-CHIEF-OF-STAFF  
Owner: Boss Ferisi

MR AI STAN is a modular personal AI command center built around a secure FastAPI backend, React/Vite web app, Chrome Browser Hands extension, and a local device bridge for authorized PC/phone administration.

## Architecture

```
MR AI STAN
├── AI Core / Orchestrator
├── Specialist Agents
├── Memory + Tasks
├── Real System Telemetry
├── Chrome Browser Hands
├── Creative Studio
├── Tracking Map (authorized location)
├── Google Protection Console
├── Local Device Bridge
└── Secure FastAPI Backend
```

AI providers:
- Gemini primary
- Kimi secondary

Database:
- SQLite phase 1
- PostgreSQL-ready architecture

## Reality-first rule

The command center must not fabricate:
- CPU/RAM/GPU values
- threat counts
- task completion
- browser actions
- email sends
- device operations
- research results

An action is shown as completed only after the corresponding subsystem returns evidence.

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Important environment values remain server-side:

- `GEMINI_API_KEY`
- `KIMI_API_KEY`
- `SECRET_KEY`

## Web

```bash
cd web
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

The web app includes:
- responsive command center
- persistent NORMAL/WORKING mood with red accent in WORKING mode
- a keyboard shortcut: Ctrl+Shift+M toggles the mode
- real backend telemetry
- agent catalog and mission planner
- browser hands controls
- authorized device lab
- editable graphic canvas
- voice input through the browser Speech API
- verified activity stream
- real OpenStreetMap map with browser geolocation permission
- Google Security Checkup, recent security events, and Gmail activity entry points

## Browser Hands

Load the extension:

1. Open `chrome://extensions`
2. Enable Developer mode
3. Load unpacked
4. Select `MR-AI-STAN/extension`

Browser Hands can perform authorized page-level operations:
- read visible page data
- navigate to HTTP(S) pages
- click elements
- type into form fields
- scroll
- drag page elements through pointer events

Platform-specific posting or editing flows still depend on the target site's UI, permissions and account state. The system must never claim a post succeeded without verification.

## Local Device Bridge

The device bridge runs on the operator's own computer, not inside the Codespace.

```text
device-bridge/
├── bridge.py
├── requirements.txt
└── README.md
```

It supports authorized:
- ADB device discovery
- Android model/version/security information
- battery and storage diagnostics
- logcat collection
- reboot to system/recovery/bootloader
- fastboot device discovery
- Bluetooth LE discovery
- firmware flashing with explicit confirmation and SHA-256 verification

Requirements:
- Python 3.11+
- Android Platform Tools (`adb`, `fastboot`)
- USB debugging + device authorization for ADB
- Bluetooth hardware for BLE scans

The bridge intentionally does not implement:
- lock bypass
- FRP bypass
- iCloud/activation bypass
- credential theft
- unauthorized device access
- destructive attack tooling

## Development quality gates

GitHub Actions runs:
- Python compilation
- backend tests
- frontend production build
- Chrome extension JavaScript syntax checks

Run local backend tests:

```bash
cd backend
pytest -q
```

## Codespaces

The repository includes `.devcontainer/devcontainer.json` with automatic forwarding for:

- `8000` — backend
- `5173` — frontend

The devcontainer also starts `start.sh` after the container starts.

## Security principles

- AI provider keys remain server-side.
- External actions follow explicit permission boundaries.
- High-risk device/security operations require confirmation.
- Secrets are excluded by `.gitignore`.
- Verified activity is recorded by the backend.


## Free-first tools

The UI favors tools that do not require a paid map or desktop automation subscription:
- OpenStreetMap for the geographic map, with attribution
- Browser Speech API for voice input and the existing speech-synthesis voice output
- Chrome extension APIs for authorized page-level browser hands
- ADB/Fastboot, psutil and Bleak for local device and sensor work
- HTML Canvas for editable poster/banner creation

### Tracking and Google protection boundary

MR AI STAN shows location only from an authorized source. The Tracking Map can request the operator's browser location permission and plot the verified coordinates on OpenStreetMap.

Gmail itself can expose recent account access IP addresses and approximate locations through Google's Last account activity page. MR AI does not convert an arbitrary person's IP into a hidden GPS tracker. For future Google Workspace integration, use an authorized Google OAuth/Admin Reports connection and keep the source data attributable.

The Google Protection panel links directly to Google's official Security Checkup, recent security events, and Gmail. It never asks MR AI for a Google password.
