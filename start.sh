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

mkdir -p "$RUNTIME_DIR"

info() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

tail_log() {
  local file="$1"
  if [[ -f "$file" ]]; then
    tail -n 80 "$file"
  else
    echo "Log file not created: $file"
  fi
}

stop_pidfile() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$pid_file"
  fi
}

stop_matching_processes() {
  local pattern="$1"
  local pids
  pids="$(pgrep -f "$pattern" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    while read -r pid; do
      [[ "$pid" =~ ^[0-9]+$ ]] || continue
      kill "$pid" 2>/dev/null || true
    done <<< "$pids"
    sleep 1
  fi
}

process_alive() {
  local pid_file="$1"
  local signature="$2"
  [[ -f "$pid_file" ]] || return 1

  local pid command
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1

  command="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$command" == *"$signature"* ]]
}

wait_for_service() {
  local label="$1"
  local url="$2"
  local pid_file="$3"
  local signature="$4"
  local log_file="$5"

  for _ in {1..30}; do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      info "$label is healthy: $url"
      return 0
    fi

    if [[ -f "$pid_file" ]] && ! process_alive "$pid_file" "$signature"; then
      info "$label process is not running."
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
echo "Runtime logs: $RUNTIME_DIR"

# Stop only known project processes. The old script used pkill -f with a pattern
# that also matched this very shell script, which could terminate startup itself.
stop_pidfile "$BACKEND_PID"
stop_pidfile "$FRONTEND_PID"
stop_matching_processes '[u]vicorn app\.main:app'
stop_matching_processes '[v]ite'

# Prefer Python 3.12 because the project/runtime is intended to use it.
PYTHON_BIN="${MR_AI_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.12)"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: Python 3 is not installed."
  exit 1
fi

PYTHON_VERSION="$("$PYTHON_BIN" --version 2>&1)"
info "Using $PYTHON_VERSION"

if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]] || ! "$BACKEND_DIR/.venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1; then
  info "Preparing backend virtual environment"
  rm -rf "$BACKEND_DIR/.venv"

  if ! "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv" >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1 && [[ "$PYTHON_VERSION" == Python\ 3.12.* ]]; then
      info "Python 3.12 venv support is missing; installing python3.12-venv"
      sudo apt-get update
      sudo apt-get install -y python3.12-venv
      "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
    else
      echo "ERROR: Could not create backend/.venv."
      exit 1
    fi
  fi
fi

PYTHON="$BACKEND_DIR/.venv/bin/python"

if [[ -n "${DATABASE_URL:-}" ]]; then
  info "Using DATABASE_URL from the Codespace environment."
  if [[ -f "$BACKEND_DIR/.env" ]]; then
    if grep -q '^DATABASE_URL=' "$BACKEND_DIR/.env"; then
      sed -i "s|^DATABASE_URL=.*|DATABASE_URL=$DATABASE_URL|" "$BACKEND_DIR/.env"
    else
      printf '\nDATABASE_URL=%s\n' "$DATABASE_URL" >> "$BACKEND_DIR/.env"
    fi
  else
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=$DATABASE_URL|" "$BACKEND_DIR/.env"
  fi
elif [[ ! -f "$BACKEND_DIR/.env" ]]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  info "Created backend/.env from backend/.env.example"
fi

CURRENT_SECRET="$(sed -n 's/^SECRET_KEY=//p' "$BACKEND_DIR/.env" | head -n 1)"
if [[ -z "$CURRENT_SECRET" || "$CURRENT_SECRET" == "CHANGE_ME_TO_A_LONG_RANDOM_SECRET" || "$CURRENT_SECRET" == "CHANGE_THIS_SECRET_KEY" ]]; then
  GENERATED_SECRET="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  if grep -q '^SECRET_KEY=' "$BACKEND_DIR/.env"; then
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$GENERATED_SECRET/" "$BACKEND_DIR/.env"
  else
    printf '\nSECRET_KEY=%s\n' "$GENERATED_SECRET" >> "$BACKEND_DIR/.env"
  fi
  info "Generated a private local JWT signing key."
fi

info "Installing backend dependencies"
"$PYTHON" -m pip install --disable-pip-version-check -q -r "$BACKEND_DIR/requirements.txt"

if [[ ! -d "$WEB_DIR/node_modules" ]]; then
  info "Installing frontend dependencies"
  if [[ -f "$WEB_DIR/package-lock.json" ]]; then
    npm --prefix "$WEB_DIR" ci
  else
    npm --prefix "$WEB_DIR" install
  fi
fi

rm -f "$BACKEND_PID" "$FRONTEND_PID"

info "Starting backend on port 8000"
printf '\n===== Backend start %s =====\n' "$(date -Is)" >> "$BACKEND_LOG"
(
  cd "$BACKEND_DIR"
  nohup "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    >> "$BACKEND_LOG" 2>&1 < /dev/null &
  echo $! > "$BACKEND_PID"
)

info "Starting frontend on port 5173"
printf '\n===== Frontend start %s =====\n' "$(date -Is)" >> "$FRONTEND_LOG"
(
  cd "$WEB_DIR"
  nohup npm run dev -- --host 0.0.0.0 --port 5173 \
    >> "$FRONTEND_LOG" 2>&1 < /dev/null &
  echo $! > "$FRONTEND_PID"
)

echo
echo "Local app URLs:"
echo "  Frontend: $FRONTEND_URL"
echo "  Backend:  http://127.0.0.1:8000"
echo "  Health:   $HEALTH_URL"
echo
echo "Codespace: open port 5173 for the MR AI browser interface."
echo "Backend port 8000 stays internal to the Codespace and is proxied through 5173."
echo "Set port 5173 to Public there when you need a public browser link."

wait_for_service "Backend" "$HEALTH_URL" "$BACKEND_PID" "uvicorn app.main:app" "$BACKEND_LOG"
wait_for_service "Frontend" "$FRONTEND_URL" "$FRONTEND_PID" "npm run dev" "$FRONTEND_LOG"

info "MR AI STAN startup checks passed."
