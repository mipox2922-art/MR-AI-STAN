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

For Codespaces, set `GMAIL_REDIRECT_URI` to the public HTTPS URL of the backend callback and register that exact URI in the Google OAuth client configuration.

The browser never receives the Gmail refresh token. The backend stores the encrypted refresh token in the database and exchanges it for short-lived access tokens when mailbox operations run.

Current connector routes:

- `GET /integrations/gmail/status`
- `GET /integrations/gmail/connect`
- `GET /integrations/gmail/callback`
- `GET /integrations/gmail/messages?q=...`
- `GET /integrations/gmail/messages/{message_id}`
- `DELETE /integrations/gmail`

Sending/replying is intentionally not enabled in this tranche. High-impact mail actions will use the existing approval engine before execution.
