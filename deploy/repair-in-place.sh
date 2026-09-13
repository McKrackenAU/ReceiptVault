#!/usr/bin/env bash
# Back-compat wrapper. Prefer make-reachable.sh IP PORT
set -euo pipefail
APP_ROOT="${APP_ROOT:-/opt/receiptvault}"
IP="${1:-${RV_IP:-192.168.13.14}}"
PORT="${2:-${RV_PORT:-80}}"
exec bash "$APP_ROOT/deploy/make-reachable.sh" "$IP" "$PORT"
