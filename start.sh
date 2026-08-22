#!/bin/bash
set -e
cd /workspaces/MR-AI-STAN
echo "🔄 Kuzima michakato ya zamani..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1
echo "🚀 Kuanzisha backend..."
(cd backend && nohup uvicorn app.main:app --reload --port 8000 > /tmp/backend.log 2>&1 &)
sleep 2
echo "🚀 Kuanzisha frontend..."
(cd web && nohup npm run dev > /tmp/frontend.log 2>&1 &)
sleep 3
echo "🌐 Kuhakikisha port 8000 ni Public..."
gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" 2>/dev/null || \
  echo "⚠️  Fungua tab ya PORTS na uweke 8000 -> Public kwa mkono"
echo ""
echo "✅ Kuangalia hali..."
curl -s -o /dev/null -w "Backend (localhost:8000): HTTP %{http_code}\n" http://localhost:8000/health
echo "Frontend: http://localhost:5173/ (fungua kupitia tab ya PORTS)"
