#!/usr/bin/env bash
# Started by systemd. Listens on the LAN port so the browser hits ReceiptVault, not Caddy.
set -euo pipefail
cd /opt/receiptvault/backend
PORT="${RECEIPTVAULT_API_PORT:-${RECEIPTVAULT_LAN_PORT:-8082}}"
HOST="${RECEIPTVAULT_API_HOST:-0.0.0.0}"
exec /opt/receiptvault/backend/.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
