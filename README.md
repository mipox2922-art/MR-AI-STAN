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

## Production deployment (free backend + Cloudflare Pages)

The full Python app is too large for the Cloudflare Workers Free bundle limit. Deploy the FastAPI backend as a free Render Web Service using the repository's `render.yaml` Blueprint, and keep the frontend on Cloudflare Pages.

Render Blueprints need these private values supplied during setup:

- `DATABASE_URL`: the existing Supabase PostgreSQL connection string.
- `DATABASE_SSL_CA_CERT`: the trusted database CA certificate in PEM format, if the database endpoint's certificate chain is not present in the runtime trust store. The current CI database endpoint fails certificate verification without its CA. Do not disable certificate or hostname verification to work around this.
- `GMAIL_CLIENT_SECRET`: the Web OAuth Client Secret from Google Cloud.

Add the same PEM certificate as the GitHub Actions secret `DATABASE_SSL_CA_CERT` if you want the CI database smoke test to run. Without it, CI clearly reports that the live database connection check was skipped; it does not claim that Supabase connectivity was verified.

The Blueprint generates `SECRET_KEY` and sets the hosted Gmail Client ID, callback URI, least-privilege scope, and CORS origin. Optional AI provider keys can be added in the Render service's Environment settings.

After Render creates and deploys the API, copy its HTTPS service origin (for example, `https://your-service.onrender.com`). In Cloudflare Pages, open the `mr-ai-stan` project, go to **Settings → Variables and Secrets**, and add this Production variable:

`MR_AI_API_URL=https://your-service.onrender.com`

Use the actual URL Render gives you, not the example. Redeploy the Pages project after adding the variable. The `/api/*` Pages Function forwards requests to Render, keeping the browser-facing site on `https://mr-ai-stan.pages.dev`.

Render's free service may sleep after 15 minutes without traffic and take about a minute to wake up. This is the trade-off for staying at $0 without adding a payment method.

## Codespaces

Use the single browser-facing port:

```bash
bash start.sh
```

Open port **5173** for the MR AI interface. The FastAPI backend stays internal on port 8000 and is reached through the Vite proxy.

On first run, the login screen automatically switches to **Initialize operator** when the local database has no users. Create the operator account there, then use that account for subsequent sessions.

The application does not ship a hard-coded production username or password.
