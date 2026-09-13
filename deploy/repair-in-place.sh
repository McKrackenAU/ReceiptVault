#!/usr/bin/env bash
# Run inside the ReceiptVault LXC as root to make the UI reachable.
#   pct exec <CTID> -- bash /opt/receiptvault/deploy/repair-in-place.sh
set -euo pipefail
export LANG="${LANG:-C.UTF-8}" LC_ALL="${LC_ALL:-C.UTF-8}" DEBIAN_FRONTEND=noninteractive

APP_ROOT="${APP_ROOT:-/opt/receiptvault}"
ENV_FILE="${ENV_FILE:-/etc/receiptvault/receiptvault.env}"

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root inside the container (pct exec <CTID> -- bash $0)"
  exit 1
fi
if [[ ! -d "$APP_ROOT/backend" ]]; then
  echo "Missing $APP_ROOT — this is not a ReceiptVault container."
  exit 1
fi

id receiptvault >/dev/null 2>&1 || useradd --system --home "$APP_ROOT" --shell /usr/sbin/nologin receiptvault
install -d -m 0755 "$APP_ROOT" /var/lib/receiptvault/{evidence,derived,staging,backups} /etc/caddy
chown -R receiptvault:receiptvault "$APP_ROOT" /var/lib/receiptvault

export PATH="/usr/local/bin:/usr/bin:$PATH"
if [[ ! -x "$APP_ROOT/backend/.venv/bin/uvicorn" ]]; then
  echo "Installing Python environment"
  cd "$APP_ROOT/backend"
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
  runuser -u receiptvault -- env PATH="$PATH" uv sync --frozen --no-dev || \
    runuser -u receiptvault -- env PATH="$PATH" uv sync --no-dev
fi
ln -sfn "$APP_ROOT/backend/.venv" "$APP_ROOT/.venv"
ln -sfn "$APP_ROOT/backend/.venv/bin/receiptvault" /usr/local/bin/receiptvault

if [[ ! -f "$APP_ROOT/frontend/dist/index.html" ]]; then
  echo "Building web UI"
  cd "$APP_ROOT/frontend"
  if [[ -f package-lock.json ]]; then
    runuser -u receiptvault -- env PATH="$PATH" npm ci
  else
    runuser -u receiptvault -- env PATH="$PATH" npm install
  fi
  runuser -u receiptvault -- env PATH="$PATH" npm run build
fi
chmod -R a+rX "$APP_ROOT/frontend/dist"

if [[ -f "$APP_ROOT/deploy/systemd/receiptvault.service" ]]; then
  install -m 0644 "$APP_ROOT/deploy/systemd/receiptvault.service" /etc/systemd/system/receiptvault.service
  install -m 0644 "$APP_ROOT/deploy/systemd/receiptvault-worker.service" /etc/systemd/system/receiptvault-worker.service
fi

LAN_PORT=80
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
  LAN_PORT="${RECEIPTVAULT_LAN_PORT:-80}"
fi
if [[ "$LAN_PORT" == "80" ]]; then
  LISTENS=":80, :8080"
else
  LISTENS=":80, :${LAN_PORT}"
fi
sysctl -w net.ipv4.ip_unprivileged_port_start=0 >/dev/null 2>&1 || true
mkdir -p /etc/sysctl.d
echo 'net.ipv4.ip_unprivileged_port_start=0' >/etc/sysctl.d/20-receiptvault-ports.conf

cat >/etc/caddy/Caddyfile <<EOF
${LISTENS} {
	encode gzip
	request_body {
		max_size 60MB
	}
	handle /api/* {
		reverse_proxy 127.0.0.1:8473
	}
	handle /health* {
		reverse_proxy 127.0.0.1:8473
	}
	handle {
		root * ${APP_ROOT}/frontend/dist
		try_files {path} /index.html
		file_server
	}
}
EOF

systemctl daemon-reload
systemctl enable postgresql redis-server caddy receiptvault receiptvault-worker >/dev/null
systemctl restart postgresql redis-server || true
systemctl restart receiptvault receiptvault-worker caddy

ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8473/health/live >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "API still not healthy. Last logs:"
  journalctl -u receiptvault -n 40 --no-pager || true
  exit 1
fi

IP="$(hostname -I | awk '{print $1}')"
echo "READY"
echo "Open: http://${IP}/"
echo "Also: http://${IP}:8080/"
echo "Health: $(curl -fsS http://127.0.0.1:8473/health/live)"
