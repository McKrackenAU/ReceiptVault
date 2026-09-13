#!/usr/bin/env bash
# ReceiptVault listens on :80 itself. Caddy is not used.
set -euo pipefail
cd /opt/receiptvault/backend
PORT="${RECEIPTVAULT_API_PORT:-${RECEIPTVAULT_LAN_PORT:-80}}"
HOST="${RECEIPTVAULT_API_HOST:-0.0.0.0}"
exec /opt/receiptvault/backend/.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
