#!/usr/bin/env bash
# Purge Caddy and put ReceiptVault on http://<ip>/ (port 80).
#
#   pct exec <CTID> -- bash /opt/receiptvault/deploy/make-reachable.sh 192.168.13.14
set -euo pipefail
export LANG="${LANG:-C.UTF-8}" LC_ALL="${LC_ALL:-C.UTF-8}" DEBIAN_FRONTEND=noninteractive

APP_ROOT="${APP_ROOT:-/opt/receiptvault}"
ENV_FILE="${ENV_FILE:-/etc/receiptvault/receiptvault.env}"
if [[ -f "${APP_ROOT}/deploy/lib-network.sh" ]]; then
  # shellcheck source=lib-network.sh
  source "${APP_ROOT}/deploy/lib-network.sh"
fi
IP="${1:-${RV_IP:-${PREFERRED_LXC_IP:-192.168.13.14}}}"
PUBLIC_PORT="${2:-${RV_PORT:-80}}"
CIDR="${RV_CIDR:-}"
GATEWAY="${RV_GATEWAY:-}"

if [[ "$IP" != */* ]]; then
  CIDR="${CIDR:-}"
else
  CIDR="$IP"
  IP="${IP%%/*}"
fi
if [[ -z "$CIDR" ]]; then
  if command -v normalize_ipv4_cidr >/dev/null 2>&1; then
    CIDR="$(normalize_ipv4_cidr "$IP" "${GATEWAY:-}")"
  else
    CIDR="${IP}/${DEFAULT_PREFIX:-20}"
  fi
fi
if [[ -z "$GATEWAY" ]]; then
  GATEWAY="${IP%.*}.1"
fi

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root inside the LXC (pct exec <CTID> -- bash $0 $IP)"
  exit 1
fi
if [[ ! -d "$APP_ROOT/backend" ]]; then
  echo "Missing $APP_ROOT"
  exit 1
fi

if [[ -f "$APP_ROOT/deploy/purge-caddy.sh" ]]; then
  bash "$APP_ROOT/deploy/purge-caddy.sh"
else
  systemctl disable --now caddy.service caddy.socket >/dev/null 2>&1 || true
  systemctl mask caddy.service >/dev/null 2>&1 || true
  pkill -9 caddy >/dev/null 2>&1 || true
  fuser -k 80/tcp >/dev/null 2>&1 || true
  apt-get purge -y caddy >/dev/null 2>&1 || true
  rm -rf /etc/caddy /usr/share/caddy
fi
systemctl disable --now receiptvault-http80.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/receiptvault-http80.service
sysctl -w net.ipv4.ip_unprivileged_port_start=0 >/dev/null 2>&1 || true

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

if [[ "$PUBLIC_PORT" == "80" ]]; then
  PUBLIC="http://${IP}"
else
  PUBLIC="http://${IP}:${PUBLIC_PORT}"
fi
install -d -m 0700 /etc/receiptvault
write_env() {
  local key="$1" value="$2"
  if [[ -f "$ENV_FILE" ]] && grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >>"$ENV_FILE"
  fi
}
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
write_env RECEIPTVAULT_PUBLIC_URL "$PUBLIC"
write_env RECEIPTVAULT_LAN_PORT "$PUBLIC_PORT"
write_env RECEIPTVAULT_API_HOST "0.0.0.0"
write_env RECEIPTVAULT_API_PORT "$PUBLIC_PORT"

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
PORT="${RECEIPTVAULT_API_PORT:-${RECEIPTVAULT_LAN_PORT:-80}}"
HOST="${RECEIPTVAULT_API_HOST:-0.0.0.0}"
exec /opt/receiptvault/backend/.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
EOF
chmod 0755 "$APP_ROOT/deploy/run-api.sh"
install -m 0644 "$APP_ROOT/deploy/systemd/receiptvault.service" /etc/systemd/system/receiptvault.service
if [[ -f "$APP_ROOT/deploy/systemd/receiptvault-worker.service" ]]; then
  install -m 0644 "$APP_ROOT/deploy/systemd/receiptvault-worker.service" /etc/systemd/system/receiptvault-worker.service
fi

systemctl daemon-reload
systemctl enable postgresql redis-server receiptvault receiptvault-worker >/dev/null
systemctl restart postgresql redis-server || true
fuser -k "${PUBLIC_PORT}/tcp" >/dev/null 2>&1 || true
systemctl restart receiptvault receiptvault-worker

ok=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${PUBLIC_PORT}/health/live" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "App did not start on port ${PUBLIC_PORT}."
  journalctl -u receiptvault -n 50 --no-pager || true
  exit 1
fi
page="$(curl -fsS "http://127.0.0.1:${PUBLIC_PORT}/" || true)"
if echo "$page" | grep -qi 'Your web server is working'; then
  echo "Port ${PUBLIC_PORT} is still Caddy. Purge failed."
  exit 1
fi

echo
echo "ReceiptVault is ready."
echo "Open this URL:"
echo "  ${PUBLIC}"
echo
ip -4 addr show eth0 | sed -n 's/.*inet /eth0 /p' || true
