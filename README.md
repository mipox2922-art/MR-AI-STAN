# MR AI — Digital Chief of Staff

Project ID: MR-AI-CHIEF-OF-STAFF  
Owner: Boss Ferisi

## Architecture

- React + Vite web app
- Chrome MV3 extension (Browser Hands)
- FastAPI backend hosted on Render
- PostgreSQL for durable hosted data; SQLite for local development only
- OpenRouter AI provider (defaults to the free-model router), with Mistral, Grok/xAI, Gemini, and Kimi also supported

AI provider keys and OAuth refresh tokens must remain server-side. Never put `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY`, `KIMI_API_KEY`, or Gmail client secrets in React or extension code.

## Local development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Web app

```bash
cd web
npm ci
npm run dev
```

### Chrome extension

Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, then select the repository's `extension` directory.

## Free deployment target: Render + Neon

The production setup is intended to stay within free tiers. Do not enable paid Render compute or Cloudflare Containers.

### Backend (already created on Render)

- Service URL: [https://mr-ai-stan.onrender.com](https://mr-ai-stan.onrender.com)
- Branch: `main`
- Compute: **Free**
- Dockerfile: `backend/Dockerfile`
- Docker build context: `backend`
- Root Directory: leave blank when the Dockerfile and context above are configured from the repository root.

Required Render environment variables:

- `SECRET_KEY`: unique random secret; at least 32 characters.
- `DATABASE_URL`: connection string from a PostgreSQL provider such as Neon. Do not leave production data on the container's local SQLite file.
- `CORS_ORIGINS`: `https://mr-ai-stan-web.onrender.com,http://localhost:5173`
- `SCHEDULER_ENABLED`: `false` on the free web service.

Optional AI variables: `OPENROUTER_API_KEY` (recommended when using OpenRouter) and `OPENROUTER_MODEL` (defaults to `openrouter/free`), `MISTRAL_API_KEY` / `MISTRAL_MODEL`, `XAI_API_KEY` / `GROK_MODEL`, or `GEMINI_API_KEY` / `KIMI_API_KEY`. OpenRouter is the default. Mistral and Grok model calls may incur charges based on your provider account and selected model, so check their pricing before selecting them. Optional Gmail variables: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`, and `GMAIL_SCOPES`. OpenRouter free models have usage limits and availability can vary.

Render Free instances can spin down when idle and their local filesystem is not durable. Configure PostgreSQL before creating the first owner account or relying on saved Tasks, Memory, or Gmail tokens.

### Frontend (Render Static Site)

The root `render.yaml` defines the free static frontend:

- Name: `mr-ai-stan-web`
- Root directory: `web`
- Build command: `npm ci && npm run build`
- Publish directory: `dist`
- Build-time `VITE_API_URL`: `https://mr-ai-stan.onrender.com`

Create it through Render's **New → Blueprint** flow using this repository and `render.yaml`, or use **New → Static Site** and enter the same settings. The frontend origin should be `https://mr-ai-stan-web.onrender.com`; if Render assigns a different URL, update `CORS_ORIGINS` on the backend to the actual URL.

The frontend API client uses `VITE_API_URL` in production. Local development can continue using the Vite `/api` proxy.

### Verify the deployment

1. Open [backend health](https://mr-ai-stan.onrender.com/health). It should return `{"status":"healthy","database":"reachable"}` when PostgreSQL is correctly configured.
2. Open `https://mr-ai-stan-web.onrender.com`, create the initial owner account, then sign in.
3. Test AI Core, Tasks, Memory, and reload the app to confirm data persists.
4. Only enable Gmail after the credentials and redirect URI are configured.

### Unattended scheduled work

The GitHub Actions workflow `.github/workflows/mr-ai-scheduler.yml` triggers the backend every 15 minutes and can also be run manually. It wakes the Render Free backend, confirms the database health check, and then calls the protected scheduler endpoint.

The workflow uses GitHub Actions OIDC instead of a shared secret. The backend validates GitHub's signed token against GitHub's public signing keys and checks the exact repository, `main` branch, workflow file, event type, audience, issuer, and token expiry. No `MR_AI_CRON_SECRET` GitHub secret is required. The backend keeps support for the legacy `CLOUDFLARE_CRON_SECRET` header for existing trusted callers.

Keep `SCHEDULER_ENABLED=false` on the Render Free web service if you want GitHub Actions to be the sole polling trigger. GitHub scheduled runs can be delayed; this is periodic execution, not a real-time or guaranteed-at-the-exact-minute worker. If the backend does not become healthy or identity verification fails, the workflow fails closed and does not process work.

Scheduled commands containing `job research Python developer` can search the public RemoteOK and Remotive feeds and save the verified search result to the task record. No application is submitted automatically.

## Gmail OAuth

For the Render backend, use this callback URI in Render environment variables and Google Cloud Console:

`https://mr-ai-stan.onrender.com/integrations/gmail/callback`

Configure `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, and `GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly`. The browser must never receive a Gmail refresh token. Sending/replying is not enabled by the current read-only integration.

## Health and authentication

- `GET /health` checks both the API process and database connection.
- The first account is created through the **Initialize operator** screen when there are no users.
- The API does not ship a hard-coded production username or password.
