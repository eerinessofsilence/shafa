#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
BACKEND_HOST="${SHAFA_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${SHAFA_BACKEND_PORT:-8000}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
NPM_CMD="${NPM_CMD:-npm}"

PYTHON_CMD=()
if [[ -n "${SHAFA_PYTHON:-}" ]]; then
  PYTHON_CMD=("$SHAFA_PYTHON")
elif [[ -x "$PROJECT_ROOT/venv/Scripts/python.exe" ]]; then
  PYTHON_CMD=("$PROJECT_ROOT/venv/Scripts/python.exe")
elif [[ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]]; then
  PYTHON_CMD=("$PROJECT_ROOT/.venv/Scripts/python.exe")
elif [[ -x "$PROJECT_ROOT/venv/bin/python" ]]; then
  PYTHON_CMD=("$PROJECT_ROOT/venv/bin/python")
elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON_CMD=("$PROJECT_ROOT/.venv/bin/python")
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=(python)
elif command -v py >/dev/null 2>&1; then
  PYTHON_CMD=(py -3)
else
  echo "Python was not found. Create .venv/venv or set SHAFA_PYTHON."
  exit 1
fi

if ! command -v "$NPM_CMD" >/dev/null 2>&1; then
  echo "npm was not found. Install Node.js or set NPM_CMD."
  exit 1
fi

backend_pid=""
frontend_pid=""
backend_started_by_script=0

cleanup() {
  local status=$?
  trap - INT TERM EXIT

  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill "$frontend_pid" 2>/dev/null || true
  fi
  if [[ "$backend_started_by_script" == "1" ]] && [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
  fi

  if [[ -n "$frontend_pid" ]]; then
    wait "$frontend_pid" 2>/dev/null || true
  fi
  if [[ "$backend_started_by_script" == "1" ]] && [[ -n "$backend_pid" ]]; then
    wait "$backend_pid" 2>/dev/null || true
  fi

  exit "$status"
}

backend_health_check() {
  local health_url="${BACKEND_URL}/health"
  "${PYTHON_CMD[@]}" - "$health_url" >/dev/null 2>&1 <<'PY'
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=1) as response:
    sys.exit(0 if response.status < 500 else 1)
PY
}

wait_for_backend() {
  local health_url="${BACKEND_URL}/health"

  for ((attempt = 1; attempt <= 60; attempt += 1)); do
    if backend_health_check; then
      return 0
    fi

    if [[ "$backend_started_by_script" == "1" ]] && ! kill -0 "$backend_pid" 2>/dev/null; then
      echo "Backend stopped before becoming ready."
      wait "$backend_pid"
      exit $?
    fi

    sleep 1
  done

  echo "Backend did not become ready at ${health_url}."
  return 1
}

trap cleanup INT TERM EXIT

cd "$PROJECT_ROOT"
export SHAFA_BACKEND_PORT="$BACKEND_PORT"
export SHAFA_API_BASE_URL="${SHAFA_API_BASE_URL:-$BACKEND_URL}"

if backend_health_check; then
  echo "Reusing backend: ${BACKEND_URL}"
else
  echo "Starting backend: ${BACKEND_URL}"
  "${PYTHON_CMD[@]}" -m uvicorn telegram_accounts_api.main:app \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    --reload &
  backend_pid=$!
  backend_started_by_script=1

  wait_for_backend
fi

echo "Starting frontend: npm run dev"
cd "$PROJECT_ROOT/desktop-ui"
"$NPM_CMD" run dev &
frontend_pid=$!

while true; do
  if [[ "$backend_started_by_script" == "1" ]] && ! kill -0 "$backend_pid" 2>/dev/null; then
    wait "$backend_pid"
    exit $?
  fi

  if ! kill -0 "$frontend_pid" 2>/dev/null; then
    wait "$frontend_pid"
    exit $?
  fi

  sleep 1
done
