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

## Production deployment (Cloudflare Pages + Cloudflare Containers)

MR AI is hosted on Cloudflare for both the browser app and FastAPI API:

- **Frontend:** Cloudflare Pages project `mr-ai-stan`, served at `https://mr-ai-stan.pages.dev`.
- **Backend:** FastAPI inside a Cloudflare Container managed by the Worker `mr-ai-stan-api`.
- **API routing:** the Pages Function forwards same-origin `/api/*` requests through the `MR_AI_API` service binding. No Render API URL is needed.
- **Database:** a reachable PostgreSQL database is required for durable production data. Supabase is one option, not a code-level requirement; configure `DATABASE_URL` for any supported PostgreSQL provider. Cloudflare Container local disk is ephemeral, and Cloudflare D1 is not a drop-in SQLAlchemy/PostgreSQL replacement. Keep SQLite for local development only.

**Plan and cost:** Cloudflare Containers require the Workers Paid plan and may incur usage-based container charges. Review the [official Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/) before enabling deployment.

### 1. GitHub Actions deployment credentials

In GitHub, open **Settings → Secrets and variables → Actions → New repository secret** and add:

- `CLOUDFLARE_API_TOKEN`: account-scoped token authorized to deploy Workers and Containers.
- `CLOUDFLARE_ACCOUNT_ID`: the Cloudflare account ID that owns the Pages project and API Worker.

The workflow `.github/workflows/deploy-cloudflare-api.yml` deploys the API Worker when backend files change on `main`, or manually from **GitHub → Actions → Deploy MR AI API to Cloudflare Containers → Run workflow**. If either credential is missing, an automatic push safely skips backend deployment and records a warning; manual deployment fails clearly.

### 2. Configure API Worker runtime secrets

After the first successful Worker deployment, open **Cloudflare Dashboard → Workers & Pages → mr-ai-stan-api → Settings → Variables and Secrets**. Add the required secrets:

- `SECRET_KEY`: a unique random value at least 32 characters long.
- `DATABASE_URL`: PostgreSQL connection string supplied by your chosen database provider.
- `CLOUDFLARE_CRON_SECRET`: a separate random value at least 32 characters long, used to authenticate scheduled work.

Add these only when needed:

- `DATABASE_SSL_CA_CERT`: custom trusted CA certificate in PEM format if your PostgreSQL provider requires one. It is optional when the system trust store already validates the database certificate. Never disable TLS verification.
- `GEMINI_API_KEY` and/or `KIMI_API_KEY`: for the AI provider(s) you use.
- `GMAIL_CLIENT_SECRET`: if Gmail OAuth is enabled.

The non-secret defaults in `backend/wrangler.jsonc` set the Pages CORS origin, Gmail client ID/redirect URI, and scheduler configuration. If your public Pages hostname changes, update `CORS_ORIGINS` in the Worker configuration and `GMAIL_REDIRECT_URI` in both Google Cloud Console and the Worker config.

### 3. Connect Cloudflare Pages to the API Worker

The Pages project must be connected to this Git repository, with `web` as its root directory, `npm run build` as the build command, and `dist` as the output directory. Keep `web/wrangler.jsonc` in the deployment configuration so the Production service binding named `MR_AI_API` targets the Worker `mr-ai-stan-api`.

After deployment, open `https://mr-ai-stan.pages.dev/api/health`. It should return `{"status":"healthy","database":"reachable"}` when the backend container and database are reachable. A healthy Pages build alone does not prove runtime secrets or the live database connection are correct.

Register this Gmail OAuth redirect URI in Google Cloud Console if Gmail integration is enabled:

`https://mr-ai-stan.pages.dev/api/integrations/gmail/callback`.

## Codespaces

Use the single browser-facing port:

```bash
bash start.sh
```

Open port **5173** for the MR AI interface. The FastAPI backend stays internal on port 8000 and is reached through the Vite proxy.

On first run, the login screen automatically switches to **Initialize operator** when the local database has no users. Create the operator account there, then use that account for subsequent sessions.

The application does not ship a hard-coded production username or password.
