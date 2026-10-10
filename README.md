# MR AI — Digital Chief of Staff

Project ID: MR-AI-CHIEF-OF-STAFF

Owner: Boss Ferisi

## Architecture

WEB APP
+
CHROME EXTENSION
+
SHARED SECURE FASTAPI BACKEND

AI:
- Gemini primary
- Kimi secondary

Database:
- SQLite Phase 1
- PostgreSQL-ready architecture

## Security

AI provider API keys remain server-side.

Never place:
GEMINI_API_KEY
KIMI_API_KEY

inside React or browser extension code.

## Backend

cd backend

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

## Web

cd web

npm install
npm run dev

## Extension

Chrome:
chrome://extensions

Enable:
Developer mode

Then:
Load unpacked

Select:
MR-AI-STAN/extension

## Gmail connector

The first Gmail integration uses server-side OAuth and the least-privilege `gmail.readonly` scope for mailbox search/read.

Add these values to `backend/.env`:

```env
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REDIRECT_URI=http://localhost:8000/integrations/gmail/callback
GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly
```

For the hosted site, the registered Google OAuth redirect URI is:

`https://mr-ai-stan.pages.dev/api/integrations/gmail/callback`

The browser never receives the Gmail refresh token. The backend stores the encrypted refresh token in the database and exchanges it for short-lived access tokens when mailbox operations run.

Current connector routes:

- `GET /integrations/gmail/status`
- `GET /integrations/gmail/connect`
- `GET /integrations/gmail/callback`
- `GET /integrations/gmail/messages?q=...`
- `GET /integrations/gmail/messages/{message_id}`
- `DELETE /integrations/gmail`

Sending/replying is intentionally not enabled in this tranche. High-impact mail actions will use the existing approval engine before execution.

## Production deployment (Render only)

The root `render.yaml` Blueprint defines both application services on Render:

- **Frontend:** Render Static Site, service name `mr-ai-stan-web` (normally `https://mr-ai-stan-web.onrender.com`).
- **Backend:** FastAPI web service, service name `mr-ai-stan-api` (normally `https://mr-ai-stan-api.onrender.com`).

Cloudflare Pages, Cloudflare Functions, and Supabase are **not required**. Render wires the frontend's build-time `VITE_API_URL` to the backend's `RENDER_EXTERNAL_URL`, and the API allows the Render frontend origin through CORS.

### Deploy

1. In Render, create or open the Blueprint for this repository and sync `render.yaml`.
2. Configure the backend's `GEMINI_API_KEY` and/or `KIMI_API_KEY` in Render Environment settings. Configure `GMAIL_CLIENT_SECRET` only if Gmail OAuth is enabled.
3. Configure persistent storage deliberately before using the app with important data. The app supports SQLite by default for local/sandbox use and accepts a PostgreSQL `DATABASE_URL`. The Blueprint does not provision a third-party database.
4. After Render deploys both services, check the backend health endpoint:
   `https://mr-ai-stan-api.onrender.com/health`
   It should return `{"status":"healthy","database":"reachable"}` when the configured database is reachable.
5. In Google Cloud Console, register this exact authorized redirect URI if Gmail integration is enabled:
   `https://mr-ai-stan-api.onrender.com/integrations/gmail/callback`.

**Persistence warning:** a free Render web service does not provide durable local-file storage. If `DATABASE_URL` is left on SQLite, data can be lost when the instance restarts or is redeployed. For durable production data, configure a Render-managed PostgreSQL database on an appropriate plan or use a paid persistent disk. Do not substitute a temporary free database that expires after 30 days. PostgreSQL TLS certificate and hostname verification must remain enabled; provide `DATABASE_SSL_CA_CERT` only when your database requires a custom trusted CA.

If Render assigns a different public hostname to either service, use the actual hostname in `CORS_ORIGINS`, `VITE_API_URL`, and the Google OAuth redirect URI. The Chrome extension's production defaults currently target the service names declared in `render.yaml`.

## Codespaces

Use the single browser-facing port:

```bash
bash start.sh
```

Open port **5173** for the MR AI interface. The FastAPI backend stays internal on port 8000 and is reached through the Vite proxy.

On first run, the login screen automatically switches to **Initialize operator** when the local database has no users. Create the operator account there, then use that account for subsequent sessions.

The application does not ship a hard-coded production username or password.
