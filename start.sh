#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BACKEND_DIR="$ROOT_DIR/backend"
WEB_DIR="$ROOT_DIR/web"
RUNTIME_DIR="$ROOT_DIR/.runtime"
BACKEND_LOG="$RUNTIME_DIR/backend.log"
FRONTEND_LOG="$RUNTIME_DIR/frontend.log"
BACKEND_PID="$RUNTIME_DIR/backend.pid"
FRONTEND_PID="$RUNTIME_DIR/frontend.pid"
HEALTH_URL="http://127.0.0.1:8000/health"
FRONTEND_URL="http://127.0.0.1:5173/"
PYTHON_BIN="${MR_AI_PYTHON:-$(command -v python3.12 2>/dev/null || command -v python3 2>/dev/null || true)}"

mkdir -p "$RUNTIME_DIR"

info() { printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }

tail_log() {
  local file="$1"
  if [[ -f "$file" ]]; then
    tail -n 80 "$file"
  else
    echo "Log file not created: $file"
  fi
}

process_from_pidfile_alive() {
  local pid_file="$1"
  local signature="$2"
  local pid command

  [[ -f "$pid_file" ]] || return 1
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    return 1
  fi

  command="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  if [[ "$command" == *"$signature"* ]]; then
    return 0
  fi

  rm -f "$pid_file"
  return 1
}

wait_for_service() {
  local label="$1"
  local url="$2"
  local pid_file="$3"
  local signature="$4"
  local log_file="$5"
  local attempt

  for attempt in {1..30}; do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      info "$label is healthy: $url"
      return 0
    fi

    if ! process_from_pidfile_alive "$pid_file" "$signature"; then
      info "$label process exited before becoming healthy."
      echo "----- $label LOG: $log_file -----"
      tail_log "$log_file"
      echo "--------------------------------"
      return 1
    fi
    sleep 1
  done

  info "$label did not become healthy within 30 seconds."
  echo "----- $label LOG: $log_file -----"
  tail_log "$log_file"
  echo "--------------------------------"
  return 1
}

info "MR AI STAN startup"
echo "Repository: $ROOT_DIR"
echo "Logs: $RUNTIME_DIR"

if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: No Python interpreter found."
  exit 1
fi

if [[ "$("$PYTHON_BIN" --version 2>&1)" != Python\ 3.12.* ]]; then
  info "Preferred Python 3.12 is unavailable; using $("$PYTHON_BIN" --version 2>&1)."
fi

# The Ubuntu image can include Python 3.12 without the venv/ensurepip package.
# Install that package only when we actually need to create the project venv.
if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  info "Preparing Python virtual environment with $("$PYTHON_BIN" --version 2>&1)"
  if ! "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv" >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1 && [[ "$("$PYTHON_BIN" --version 2>&1)" == Python\ 3.12.* ]]; then
      info "Python venv support is missing; installing python3.12-venv"
      sudo apt-get update
      sudo apt-get install -y python3.12-venv
      rm -rf "$BACKEND_DIR/.venv"
      "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
    else
      echo "ERROR: Cannot create backend/.venv and automatic package installation is unavailable."
      echo "Interpreter: $PYTHON_BIN"
      "$PYTHON_BIN" --version || true
      exit 1
    fi
  fi
fi

PYTHON="$BACKEND_DIR/.venv/bin/python"

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  info "Created backend/.env from backend/.env.example"
fi

info "Installing/verifying backend dependencies"
"$PYTHON" -m pip install --disable-pip-version-check -q -r "$BACKEND_DIR/requirements.txt"

if [[ ! -d "$WEB_DIR/node_modules" ]]; then
  info "Installing frontend dependencies"
  if [[ -f "$WEB_DIR/package-lock.json" ]]; then
    npm --prefix "$WEB_DIR" ci
  else
    npm --prefix "$WEB_DIR" install
  fi
fi

if ! curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
  if process_from_pidfile_alive "$BACKEND_PID" "uvicorn app.main:app"; then
    info "Backend process is already running; checking its health"
  else
    info "Starting backend on port 8000"
    printf '\n===== Backend start %s =====\n' "$(date -Is)" >> "$BACKEND_LOG"
    (
      cd "$BACKEND_DIR"
      nohup "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
        >> "$BACKEND_LOG" 2>&1 < /dev/null &
      echo $! > "$BACKEND_PID"
    )
  fi
else
  info "Backend is already healthy; leaving existing process untouched"
fi

if ! curl -fsS --max-time 2 "$FRONTEND_URL" >/dev/null 2>&1; then
  if process_from_pidfile_alive "$FRONTEND_PID" "npm run dev"; then
    info "Frontend process is already running; checking its health"
  else
    info "Starting frontend on port 5173"
    printf '\n===== Frontend start %s =====\n' "$(date -Is)" >> "$FRONTEND_LOG"
    (
      cd "$WEB_DIR"
      nohup npm run dev -- --host 0.0.0.0 --port 5173 \
        >> "$FRONTEND_LOG" 2>&1 < /dev/null &
      echo $! > "$FRONTEND_PID"
    )
  fi
else
  info "Frontend is already healthy; leaving existing process untouched"
fi

echo
echo "Local app URLs:"
echo "  Frontend: $FRONTEND_URL"
echo "  Backend:  http://127.0.0.1:8000"
echo "  Health:   $HEALTH_URL"
echo
echo "Codespaces port forwarding is declared in .devcontainer/devcontainer.json."
echo "If GitHub CLI cannot change port visibility, use the Ports panel; service startup continues."

if [[ -n "${CODESPACE_NAME:-}" ]] && command -v gh >/dev/null 2>&1; then
  if gh codespace ports visibility 5173:public 8000:public -c "$CODESPACE_NAME" >/dev/null 2>&1; then
    info "Requested public visibility for ports 5173 and 8000"
  else
    info "GitHub CLI could not change port visibility; this does not stop local services."
  fi

  gh codespace ports --json sourcePort,browseUrl,visibility -c "$CODESPACE_NAME" \
    --jq '.[] | select(.sourcePort == 8000 or .sourcePort == 5173) | "\(.sourcePort) | \(.visibility) | \(.browseUrl)"' \
    2>/dev/null || true
fi

wait_for_service "Backend" "$HEALTH_URL" "$BACKEND_PID" "uvicorn app.main:app" "$BACKEND_LOG" || exit 1
wait_for_service "Frontend" "$FRONTEND_URL" "$FRONTEND_PID" "npm run dev" "$FRONTEND_LOG" || exit 1

info "MR AI STAN startup checks passed."
