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

## Production deployment (Cloudflare + Supabase only)

The production stack is intentionally limited to these services:

- **Frontend:** Cloudflare Pages at `https://mr-ai-stan.pages.dev`.
- **Backend:** the existing FastAPI app packaged in `backend/Dockerfile`, running in a Cloudflare Container managed by the `mr-ai-stan-api` Worker.
- **Database:** Supabase PostgreSQL.

There is no Render service and no external API-origin URL. The Pages Function forwards `/api/*` requests through the `MR_AI_API` Cloudflare service binding to the `mr-ai-stan-api` Worker.

**Plan requirement:** Cloudflare Containers require the Workers Paid plan, currently starting at **$5 USD/month**, with additional usage-based charges if included allowances are exceeded. The previous Python Worker bundle exceeded the platform bundle limit, so the backend now runs as a Linux container instead of forcing the full Python dependency set into a Worker bundle. See the [Cloudflare Containers overview](https://developers.cloudflare.com/containers/) and [current pricing](https://developers.cloudflare.com/containers/platform/pricing/).

### 1. Set up automatic backend deployment

The repository now contains `.github/workflows/deploy-cloudflare-api.yml`. It builds the backend Docker image and deploys the `mr-ai-stan-api` Worker with Wrangler from a GitHub-hosted runner that has Docker available. After this PR is merged, changes under `backend/` trigger the deployment workflow; it can also be run manually from **GitHub → Actions → Deploy MR AI API to Cloudflare Containers → Run workflow**.

Add these two GitHub Actions repository secrets before deploying:

- `CLOUDFLARE_API_TOKEN`: an account-scoped Cloudflare API token with **Workers Scripts Edit** and **Workers Containers Write** permissions. Keep this token private.
- `CLOUDFLARE_ACCOUNT_ID`: the Cloudflare account ID that owns the Workers and Pages projects.

The API token permissions are separate from the Cloudflare runtime secrets listed below. The GitHub token lets Actions publish the Worker and Container image; `DATABASE_URL`, `DATABASE_SSL_CA_CERT`, `SECRET_KEY`, and provider secrets are set in the Cloudflare Worker environment and are passed into the container only at runtime. See the [Cloudflare token permission reference](https://developers.cloudflare.com/fundamentals/api/reference/permissions/).

The workflow installs the backend's Worker tooling and deploys using `backend/wrangler.jsonc` plus the existing `backend/Dockerfile`. Keep the API Worker named `mr-ai-stan-api`; that exact name is used by the Pages service binding.

Keep the Pages project named `mr-ai-stan`. Its service binding must be named `MR_AI_API` and point to the `mr-ai-stan-api` Worker in the **Production** environment. The binding is defined in `web/wrangler.jsonc`; the Pages Function does not fall back to a remote backend URL.

### 2. Set backend secrets in Cloudflare

After the first API Worker deployment has created `mr-ai-stan-api`, open the repository in the terminal and sign Wrangler in to your Cloudflare account. (You can also add the same values in **Cloudflare Dashboard → Workers & Pages → mr-ai-stan-api → Settings → Variables and Secrets**.)

```bash
cd backend
npm install
npx wrangler login

# Set these values when prompted. Do not commit them into Git.
npx wrangler secret put DATABASE_URL
npx wrangler secret put DATABASE_SSL_CA_CERT
npx wrangler secret put SECRET_KEY
npx wrangler secret put CLOUDFLARE_CRON_SECRET

# Add these if you use the corresponding integrations/providers:
npx wrangler secret put GEMINI_API_KEY
npx wrangler secret put KIMI_API_KEY
npx wrangler secret put GMAIL_CLIENT_SECRET
```

- `DATABASE_URL` is the PostgreSQL connection string copied from the Supabase dashboard's **Connect** panel.
- `DATABASE_SSL_CA_CERT` must contain the trusted Supabase database root CA certificate in PEM format. Download the certificate from **Supabase Dashboard → Database → Settings → SSL Configuration**. The database connection in CI previously failed certificate validation; the app intentionally does not disable TLS verification to get around this. See [Supabase's Postgres SSL guidance](https://supabase.com/docs/guides/platform/ssl-enforcement).
- `SECRET_KEY` must be unique and at least 32 characters. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `CLOUDFLARE_CRON_SECRET` must be a separate random value of at least 32 characters. The Worker uses it to authorize scheduled-job cycles inside the container.
- `GEMINI_API_KEY`, `KIMI_API_KEY`, and `GMAIL_CLIENT_SECRET` are only needed for the corresponding services.

The current FastAPI app creates missing tables on first startup against Supabase. Keep `SERVERLESS_MODE=false` for this container so schema initialization runs. `SCHEDULER_ENABLED=false` disables the in-process polling loop; Cloudflare Cron triggers a protected scheduler cycle every minute instead.

### 3. Confirm the deployment

After the Worker deploy and the Pages service binding are configured:

- Open `https://mr-ai-stan.pages.dev/api/health`; it should return JSON with `{"status":"healthy"}`.
- Confirm the backend Worker deployment and Container instance are healthy in Cloudflare.
- Check Worker logs if the health endpoint or Supabase TLS connection fails.
- Add `DATABASE_URL` and `DATABASE_SSL_CA_CERT` as GitHub Actions repository secrets if you want CI to execute a real Supabase connection smoke test. If the CA secret is missing, that database smoke test is explicitly skipped; CI does not claim the live database was verified.

## Codespaces

Use the single browser-facing port:

```bash
bash start.sh
```

Open port **5173** for the MR AI interface. The FastAPI backend stays internal on port 8000 and is reached through the Vite proxy.

On first run, the login screen automatically switches to **Initialize operator** when the local database has no users. Create the operator account there, then use that account for subsequent sessions.

The application does not ship a hard-coded production username or password.
