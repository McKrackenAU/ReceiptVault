#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"
cd "$ROOT"

if ! pg_isready -q; then
  sudo pg_ctlcluster 16 main start || true
fi
if ! redis-cli ping >/dev/null 2>&1; then
  sudo redis-server --daemonize yes --bind 127.0.0.1
fi

mkdir -p var/evidence var/derived var/staging var/backups
cd "$ROOT/backend"
uv sync --extra dev
cd "$ROOT/frontend"
npm install
cd "$ROOT"

echo "Starting API on :8473 and UI on :18473"
uv run --project backend uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8473 &
cd frontend && npm run dev -- --host 0.0.0.0 --port 18473
