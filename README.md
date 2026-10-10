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

## Production deployment (Cloudflare Pages + Render + Supabase)

The deployed app uses the services together, each for its intended job:

- **Frontend:** Cloudflare Pages at `https://mr-ai-stan.pages.dev`.
- **Backend:** FastAPI API service `mr-ai-stan-api` on Render, defined in the root `render.yaml` Blueprint.
- **Database:** Supabase PostgreSQL.

### 1. Deploy the FastAPI backend on Render

In Render, create a **Blueprint** for this GitHub repository and apply `render.yaml`. The Blueprint sets the backend root directory to `backend`, installs `backend/requirements.txt`, starts Uvicorn on Render's assigned port, and checks `/health`. Render generates `SECRET_KEY` automatically.

In the Render service's **Environment** settings, set:

- `DATABASE_URL`: the PostgreSQL connection URI from Supabase Dashboard → **Connect**.
- `DATABASE_SSL_CA_CERT`: the trusted Supabase root CA certificate in PEM format. Download it from Supabase Dashboard → **Database → Settings → SSL Configuration**. PostgreSQL certificate and hostname verification stays enabled; do not bypass TLS verification.
- Optional: `GEMINI_API_KEY`, `KIMI_API_KEY`, `SEARXNG_URL`, and `GMAIL_CLIENT_SECRET` if those integrations are enabled.

The `render.yaml` Blueprint includes `CORS_ORIGINS=https://mr-ai-stan.pages.dev` and the hosted Gmail OAuth callback. Keep the callback URL registered in Google Cloud as `https://mr-ai-stan.pages.dev/api/integrations/gmail/callback`.

### 2. Connect Cloudflare Pages to Render

Open the Cloudflare Pages project named `mr-ai-stan`, then go to **Settings → Variables and Secrets → Production**. Add this variable:

`MR_AI_API_URL=https://YOUR-ACTUAL-SERVICE.onrender.com`

Replace the example with the exact HTTPS origin Render assigned. Do not append `/api` or another path. Save the variable and redeploy the Pages project.

The Pages Function forwards requests from `https://mr-ai-stan.pages.dev/api/*` to the Render API. The React application keeps using the same-origin `/api` path, so the browser does not need a separate API URL and backend API keys are not exposed to the frontend.

### 3. Verify the complete connection

- Open the Render service's `/health` endpoint; it should return `{"status":"healthy"}`.
- Open `https://mr-ai-stan.pages.dev/api/health`; it should return the same JSON through the Pages proxy.
- Check Render logs for database TLS or connection errors if either health check fails.
- For the GitHub Actions Supabase smoke test, add `DATABASE_URL` and `DATABASE_SSL_CA_CERT` as repository Actions secrets. If those secrets are absent, CI explicitly skips the live database check rather than claiming Supabase was verified.


## Codespaces

Use the single browser-facing port:

```bash
bash start.sh
```

Open port **5173** for the MR AI interface. The FastAPI backend stays internal on port 8000 and is reached through the Vite proxy.

On first run, the login screen automatically switches to **Initialize operator** when the local database has no users. Create the operator account there, then use that account for subsequent sessions.

The application does not ship a hard-coded production username or password.
