#!/usr/bin/env bash
#
# EcoConstruct AI - one-command dev launcher.
#
# Starts the FastAPI backend on :8000 and the Vite frontend on :5174, then
# waits. Ctrl-C stops both.
#
#   ./start.sh            backend + frontend
#   ./start.sh backend    backend only
#   ./start.sh frontend   frontend only
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5180}"

# Pick the project's virtualenv when present, otherwise fall back to python3.
if [[ -x "$ROOT/venv/bin/python" ]]; then
  PYTHON="$ROOT/venv/bin/python"
else
  PYTHON="$(command -v python3)"
fi

run_backend() {
  echo "==> Backend  : http://localhost:${BACKEND_PORT}  (docs at /docs)"
  cd "$ROOT"
  exec "$PYTHON" -m uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT" --reload
}

run_frontend() {
  if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    echo "==> Installing frontend dependencies (first run)…"
    (cd "$ROOT/frontend" && npm install)
  fi
  echo "==> Frontend : http://localhost:${FRONTEND_PORT}"
  cd "$ROOT/frontend"
  exec npm run dev
}

target="${1:-all}"

case "$target" in
  backend)
    run_backend
    ;;
  frontend)
    run_frontend
    ;;
  all)
    # Backend in the background, frontend in the foreground.
    ( run_backend ) &
    BACKEND_PID=$!
    trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM
    # Give uvicorn a moment to bind before the browser's first request.
    sleep 3
    echo
    echo "  Open the app:  http://localhost:${FRONTEND_PORT}"
    echo
    run_frontend
    ;;
  *)
    echo "Usage: $0 [all|backend|frontend]" >&2
    exit 1
    ;;
esac
