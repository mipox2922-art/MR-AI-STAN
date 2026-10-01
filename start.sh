#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BACKEND_DIR="$ROOT_DIR/backend"
WEB_DIR="$ROOT_DIR/web"
BACKEND_LOG="/tmp/mr-ai-backend.log"
FRONTEND_LOG="/tmp/mr-ai-frontend.log"

echo "🔄 Kuzima michakato ya zamani..."
pkill -f "uvicorn.*--port 8000" 2>/dev/null || true
pkill -f "vite.*5173" 2>/dev/null || true
sleep 1

echo "🔧 Kuandaa backend environment..."
if [ ! -f "$BACKEND_DIR/.env" ]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  echo "✅ Created backend/.env from .env.example"
fi

if [ ! -x "$BACKEND_DIR/.venv/bin/python" ]; then
  echo "🐍 Creating Python virtual environment..."
  python3 -m venv "$BACKEND_DIR/.venv"
fi

echo "📦 Kuhakikisha backend dependencies..."
"$BACKEND_DIR/.venv/bin/python" -m pip install --disable-pip-version-check -q -r "$BACKEND_DIR/requirements.txt"

echo "🚀 Kuanzisha backend..."
(
  cd "$BACKEND_DIR"
  nohup "$BACKEND_DIR/.venv/bin/python" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 >"$BACKEND_LOG" 2>&1 &
)

echo "📦 Kuhakikisha frontend dependencies..."
if [ ! -d "$WEB_DIR/node_modules" ]; then
  npm --prefix "$WEB_DIR" install
fi

echo "🚀 Kuanzisha frontend..."
(
  cd "$WEB_DIR"
  nohup npm run dev -- --host 0.0.0.0 --port 5173 >"$FRONTEND_LOG" 2>&1 &
)

echo "🌐 Kuweka port 8000 kuwa Public..."
gh codespace ports visibility 8000:public -c "${CODESPACE_NAME:-}" 2>/dev/null ||   echo "⚠️ Fungua tab ya PORTS na uweke 8000 -> Public kwa mkono"

echo ""
echo "⏳ Kusubiri backend iwe tayari..."

for i in {1..20}; do
  if curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "✅ Backend (localhost:8000): HTTP 200"
    echo "✅ Frontend: http://localhost:5173/"
    exit 0
  fi
  sleep 1
done

echo "❌ Backend haikuanza ndani ya sekunde 20."
echo ""
echo "----- BACKEND LOG -----"
if [ -f "$BACKEND_LOG" ]; then
  tail -n 100 "$BACKEND_LOG"
else
  echo "Backend log haijapatikana: $BACKEND_LOG"
fi
echo "-----------------------"
echo ""
echo "Frontend log: $FRONTEND_LOG"
exit 1
