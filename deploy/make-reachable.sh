#!/usr/bin/env bash
# Put ReceiptVault on http://<ip>/ (port 80), same as other helper-script CTs.
#
# On the Proxmox host:
#   pct exec <CTID> -- bash /opt/receiptvault/deploy/make-reachable.sh 192.168.13.13
set -euo pipefail
export LANG="${LANG:-C.UTF-8}" LC_ALL="${LC_ALL:-C.UTF-8}" DEBIAN_FRONTEND=noninteractive

APP_ROOT="${APP_ROOT:-/opt/receiptvault}"
ENV_FILE="${ENV_FILE:-/etc/receiptvault/receiptvault.env}"
IP="${1:-${RV_IP:-192.168.13.13}}"
PUBLIC_PORT="${2:-${RV_PORT:-80}}"
CIDR="${RV_CIDR:-}"
GATEWAY="${RV_GATEWAY:-}"
INTERNAL_PORT=8082

if [[ "$IP" != */* ]]; then
  CIDR="${CIDR:-}"
else
  CIDR="$IP"
  IP="${IP%%/*}"
fi
if [[ -z "$GATEWAY" ]]; then
  if [[ "$IP" == "192.168.13.13" ]]; then
    GATEWAY="192.168.1.1"
  else
    GATEWAY="${IP%.*}.1"
  fi
fi
if [[ -z "$CIDR" ]]; then
  CIDR="$(python3 - "$IP" "$GATEWAY" <<'PY'
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
gw = ipaddress.ip_address(sys.argv[2])
for prefix in (24, 16, 8):
    net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    if gw in net:
        print(f"{ip}/{prefix}")
        break
else:
    print(f"{ip}/16")
PY
)"
fi

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root inside the LXC (pct exec <CTID> -- bash $0 $IP)"
  exit 1
fi
if [[ ! -d "$APP_ROOT/backend" ]]; then
  echo "Missing $APP_ROOT"
  exit 1
fi

if [[ "$PUBLIC_PORT" != "80" ]]; then
  INTERNAL_PORT="$PUBLIC_PORT"
fi

echo "Stopping Caddy (that is the page you have been seeing)"
systemctl disable --now caddy 2>/dev/null || true
systemctl mask caddy 2>/dev/null || true
fuser -k 80/tcp >/dev/null 2>&1 || true
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
if [[ -f "$ENV_FILE" ]]; then
  sed -i "s|^RECEIPTVAULT_PUBLIC_URL=.*|RECEIPTVAULT_PUBLIC_URL=${PUBLIC}|" "$ENV_FILE"
  sed -i "s|^RECEIPTVAULT_LAN_PORT=.*|RECEIPTVAULT_LAN_PORT=${INTERNAL_PORT}|" "$ENV_FILE"
  sed -i "s|^RECEIPTVAULT_API_HOST=.*|RECEIPTVAULT_API_HOST=0.0.0.0|" "$ENV_FILE"
  sed -i "s|^RECEIPTVAULT_API_PORT=.*|RECEIPTVAULT_API_PORT=${INTERNAL_PORT}|" "$ENV_FILE"
  grep -q '^RECEIPTVAULT_LAN_PORT=' "$ENV_FILE" || echo "RECEIPTVAULT_LAN_PORT=${INTERNAL_PORT}" >>"$ENV_FILE"
  grep -q '^RECEIPTVAULT_PUBLIC_URL=' "$ENV_FILE" || echo "RECEIPTVAULT_PUBLIC_URL=${PUBLIC}" >>"$ENV_FILE"
  grep -q '^RECEIPTVAULT_API_HOST=' "$ENV_FILE" || echo "RECEIPTVAULT_API_HOST=0.0.0.0" >>"$ENV_FILE"
  grep -q '^RECEIPTVAULT_API_PORT=' "$ENV_FILE" || echo "RECEIPTVAULT_API_PORT=${INTERNAL_PORT}" >>"$ENV_FILE"
else
  echo "RECEIPTVAULT_PUBLIC_URL=${PUBLIC}" >"$ENV_FILE"
  echo "RECEIPTVAULT_LAN_PORT=${INTERNAL_PORT}" >>"$ENV_FILE"
  echo "RECEIPTVAULT_API_HOST=0.0.0.0" >>"$ENV_FILE"
  echo "RECEIPTVAULT_API_PORT=${INTERNAL_PORT}" >>"$ENV_FILE"
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
PORT="${RECEIPTVAULT_API_PORT:-${RECEIPTVAULT_LAN_PORT:-8082}}"
HOST="${RECEIPTVAULT_API_HOST:-0.0.0.0}"
exec /opt/receiptvault/backend/.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
EOF
chmod 0755 "$APP_ROOT/deploy/run-api.sh"
if [[ ! -x "$APP_ROOT/deploy/lan-http80.sh" ]]; then
  cat >"$APP_ROOT/deploy/lan-http80.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
PORT="${RECEIPTVAULT_API_PORT:-${RECEIPTVAULT_LAN_PORT:-8082}}"
export RV_HTTP80_TARGET="$PORT"
exec python3 - <<'PY'
import os, socket, threading
target = int(os.environ["RV_HTTP80_TARGET"])
def pump(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listen.bind(("0.0.0.0", 80))
listen.listen(128)
while True:
    client, _ = listen.accept()
    try:
        upstream = socket.create_connection(("127.0.0.1", target), timeout=10)
    except OSError:
        client.close()
        continue
    threading.Thread(target=pump, args=(client, upstream), daemon=True).start()
    threading.Thread(target=pump, args=(upstream, client), daemon=True).start()
PY
EOF
fi
chmod 0755 "$APP_ROOT/deploy/lan-http80.sh"
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
[Install]
WantedBy=multi-user.target
EOF
cat >/etc/systemd/system/receiptvault-http80.service <<'EOF'
[Unit]
Description=ReceiptVault HTTP port 80
After=receiptvault.service
Wants=receiptvault.service
[Service]
Type=simple
EnvironmentFile=-/etc/receiptvault/receiptvault.env
ExecStart=/opt/receiptvault/deploy/lan-http80.sh
Restart=on-failure
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
if [[ "$PUBLIC_PORT" == "80" ]]; then
  systemctl enable receiptvault-http80 >/dev/null
  systemctl restart receiptvault-http80
else
  systemctl disable --now receiptvault-http80 >/dev/null 2>&1 || true
fi

HEALTH_PORT="$PUBLIC_PORT"
[[ "$PUBLIC_PORT" == "80" ]] && HEALTH_PORT=80
ok=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${HEALTH_PORT}/health/live" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "App did not start on http://127.0.0.1:${HEALTH_PORT}/"
  journalctl -u receiptvault -u receiptvault-http80 -n 50 --no-pager || true
  exit 1
fi

echo
echo "ReceiptVault is ready."
echo "Open this URL:"
echo "  ${PUBLIC}"
echo
ip -4 addr show eth0 | sed -n 's/.*inet /eth0 /p' || true
