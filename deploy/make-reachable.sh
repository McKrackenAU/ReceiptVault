#!/usr/bin/env bash
# Put ReceiptVault on a normal http://IP:PORT login page. Stops Caddy so its
# welcome page cannot appear.
#
# On the Proxmox host:
#   pct exec <CTID> -- bash /opt/receiptvault/deploy/make-reachable.sh 192.168.13.13 8082
# Or, if this file is not in the CT yet:
#   pct exec <CTID> -- env RV_IP=192.168.13.13 RV_PORT=8082 bash -s \
#     < <(curl -fsSL https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/make-reachable.sh)
set -euo pipefail
export LANG="${LANG:-C.UTF-8}" LC_ALL="${LC_ALL:-C.UTF-8}" DEBIAN_FRONTEND=noninteractive

APP_ROOT="${APP_ROOT:-/opt/receiptvault}"
ENV_FILE="${ENV_FILE:-/etc/receiptvault/receiptvault.env}"
IP="${1:-${RV_IP:-192.168.13.13}}"
PORT="${2:-${RV_PORT:-8082}}"
CIDR="${RV_CIDR:-}"
GATEWAY="${RV_GATEWAY:-}"

if [[ "$IP" != */* ]]; then
  CIDR="${CIDR:-${IP}/24}"
else
  CIDR="$IP"
  IP="${IP%%/*}"
fi
if [[ -z "$GATEWAY" ]]; then
  GATEWAY="${IP%.*}.1"
fi

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root inside the LXC (pct exec <CTID> -- bash $0 $IP $PORT)"
  exit 1
fi
if [[ ! -d "$APP_ROOT/backend" ]]; then
  echo "Missing $APP_ROOT"
  exit 1
fi

echo "Stopping Caddy (that is the page you have been seeing)"
systemctl disable --now caddy 2>/dev/null || true
systemctl mask caddy 2>/dev/null || true

if [[ -f /opt/receiptvault/deploy/guest-network.sh ]]; then
  RV_CIDR="$CIDR" RV_GATEWAY="$GATEWAY" RV_DNS="${RV_DNS:-1.1.1.1}" \
    bash /opt/receiptvault/deploy/guest-network.sh || true
else
  ip link set eth0 up || true
  if ! ip -4 addr show dev eth0 2>/dev/null | grep -q "inet ${IP}/"; then
    ip addr add "$CIDR" dev eth0 2>/dev/null || true
  fi
  ip route replace default via "$GATEWAY" 2>/dev/null || true
fi

PUBLIC="http://${IP}:${PORT}"
install -d -m 0700 /etc/receiptvault
if [[ -f "$ENV_FILE" ]]; then
  sed -i "s|^RECEIPTVAULT_PUBLIC_URL=.*|RECEIPTVAULT_PUBLIC_URL=${PUBLIC}|" "$ENV_FILE"
  sed -i "s|^RECEIPTVAULT_LAN_PORT=.*|RECEIPTVAULT_LAN_PORT=${PORT}|" "$ENV_FILE"
  sed -i "s|^RECEIPTVAULT_API_HOST=.*|RECEIPTVAULT_API_HOST=0.0.0.0|" "$ENV_FILE"
  sed -i "s|^RECEIPTVAULT_API_PORT=.*|RECEIPTVAULT_API_PORT=${PORT}|" "$ENV_FILE"
  grep -q '^RECEIPTVAULT_LAN_PORT=' "$ENV_FILE" || echo "RECEIPTVAULT_LAN_PORT=${PORT}" >>"$ENV_FILE"
  grep -q '^RECEIPTVAULT_PUBLIC_URL=' "$ENV_FILE" || echo "RECEIPTVAULT_PUBLIC_URL=${PUBLIC}" >>"$ENV_FILE"
  grep -q '^RECEIPTVAULT_API_HOST=' "$ENV_FILE" || echo "RECEIPTVAULT_API_HOST=0.0.0.0" >>"$ENV_FILE"
  grep -q '^RECEIPTVAULT_API_PORT=' "$ENV_FILE" || echo "RECEIPTVAULT_API_PORT=${PORT}" >>"$ENV_FILE"
else
  echo "RECEIPTVAULT_PUBLIC_URL=${PUBLIC}" >"$ENV_FILE"
  echo "RECEIPTVAULT_LAN_PORT=${PORT}" >>"$ENV_FILE"
  echo "RECEIPTVAULT_API_HOST=0.0.0.0" >>"$ENV_FILE"
  echo "RECEIPTVAULT_API_PORT=${PORT}" >>"$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

id receiptvault >/dev/null 2>&1 || useradd --system --home "$APP_ROOT" --shell /usr/sbin/nologin receiptvault
export PATH="/usr/local/bin:/usr/bin:$PATH"
if [[ ! -x "$APP_ROOT/backend/.venv/bin/uvicorn" ]]; then
  cd "$APP_ROOT/backend"
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
  runuser -u receiptvault -- env PATH="$PATH" uv sync --frozen --no-dev || \
    runuser -u receiptvault -- env PATH="$PATH" uv sync --no-dev
fi
if [[ ! -f "$APP_ROOT/frontend/dist/index.html" ]]; then
  cd "$APP_ROOT/frontend"
  if [[ -f package-lock.json ]]; then
    runuser -u receiptvault -- env PATH="$PATH" npm ci
  else
    runuser -u receiptvault -- env PATH="$PATH" npm install
  fi
  runuser -u receiptvault -- env PATH="$PATH" npm run build
fi
chmod -R a+rX "$APP_ROOT/frontend/dist" || true
ln -sfn "$APP_ROOT/backend/.venv" "$APP_ROOT/.venv"

mkdir -p "$APP_ROOT/deploy"
cat >"$APP_ROOT/deploy/run-api.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/receiptvault/backend
PORT="${RECEIPTVAULT_LAN_PORT:-${RECEIPTVAULT_API_PORT:-8082}}"
HOST="${RECEIPTVAULT_API_HOST:-0.0.0.0}"
exec /opt/receiptvault/backend/.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
EOF
chmod 0755 "$APP_ROOT/deploy/run-api.sh"
cat >/etc/systemd/system/receiptvault.service <<'EOF'
[Unit]
Description=ReceiptVault API
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
Type=simple
User=receiptvault
Group=receiptvault
EnvironmentFile=/etc/receiptvault/receiptvault.env
WorkingDirectory=/opt/receiptvault/backend
ExecStart=/opt/receiptvault/deploy/run-api.sh
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
if [[ -f "$APP_ROOT/deploy/systemd/receiptvault-worker.service" ]]; then
  install -m 0644 "$APP_ROOT/deploy/systemd/receiptvault-worker.service" /etc/systemd/system/receiptvault-worker.service
fi

systemctl daemon-reload
systemctl enable postgresql redis-server receiptvault receiptvault-worker >/dev/null
systemctl restart postgresql redis-server || true
systemctl restart receiptvault receiptvault-worker

ok=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${PORT}/health/live" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "App did not start on port ${PORT}."
  journalctl -u receiptvault -n 50 --no-pager || true
  exit 1
fi

echo
echo "Caddy is off. ReceiptVault is listening on ${PORT}."
echo "Open this exact URL:"
echo "  ${PUBLIC}"
echo
ip -4 addr show eth0 | sed -n 's/.*inet /eth0 /p' || true
