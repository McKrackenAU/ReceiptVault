#!/usr/bin/env bash
# Runs inside the ReceiptVault LXC as root. Do not put secrets on the invoking command line.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/receiptvault}"
ENV_FILE="${ENV_FILE:-/etc/receiptvault/receiptvault.env}"
LOG="${LOG:-/var/log/receiptvault-bootstrap.log}"
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export LANGUAGE="${LANGUAGE:-C.UTF-8}"
export DEBIAN_FRONTEND=noninteractive
export APT_LISTCHANGES_FRONTEND=none
mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

redact() { sed -E 's/(PASSWORD|SECRET|TOKEN|KEY|MASTER|REFRESH)=.*/\1=[redacted]/Ig'; }
log() { echo "[$(date -u +%FT%TZ)] $*" | redact; }

if [[ ${EUID} -ne 0 ]]; then
  echo "lxc-bootstrap.sh must run as root inside the container."
  exit 1
fi

log "Installing runtime packages"
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl git gnupg locales \
  python3 python3-venv python3-pip python3-dev build-essential \
  postgresql postgresql-contrib redis-server \
  caddy tesseract-ocr tesseract-ocr-eng ghostscript qpdf libmagic1 poppler-utils \
  libpq-dev
if [[ -f /etc/locale.gen ]]; then
  sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
  sed -i 's/^# *en_AU.UTF-8 UTF-8/en_AU.UTF-8 UTF-8/' /etc/locale.gen
fi
locale-gen >/dev/null 2>&1 || true
update-locale LANG=C.UTF-8 LC_ALL=C.UTF-8 >/dev/null 2>&1 || true
sysctl -w net.ipv4.ip_unprivileged_port_start=0 >/dev/null 2>&1 || true
mkdir -p /etc/sysctl.d
echo 'net.ipv4.ip_unprivileged_port_start=0' >/etc/sysctl.d/20-receiptvault-ports.conf

if ! command -v node >/dev/null || ! node -v | grep -qE 'v(2[0-9]|[3-9])'; then
  log "Installing Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

if ! command -v uv >/dev/null; then
  log "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
fi

id receiptvault >/dev/null 2>&1 || useradd --system --home "$APP_ROOT" --shell /usr/sbin/nologin receiptvault
install -d -m 0755 "$APP_ROOT" /var/lib/receiptvault/{evidence,derived,staging,backups}
install -d -m 0700 /etc/receiptvault
chown -R receiptvault:receiptvault "$APP_ROOT" /var/lib/receiptvault

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — the host installer should have written it."
  exit 1
fi
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

log "Starting PostgreSQL and Redis"
systemctl enable --now postgresql redis-server

DB_URL="${RECEIPTVAULT_DATABASE_URL:-}"
DB_PASS="$(python3 - <<'PY'
import urllib.parse, os
url = os.environ.get("RECEIPTVAULT_DATABASE_URL", "")
print(urllib.parse.urlparse(url).password or "")
PY
)"
runuser -u postgres -- psql -v ON_ERROR_STOP=0 -c "CREATE USER receiptvault LOGIN PASSWORD '${DB_PASS}';" || true
runuser -u postgres -- psql -v ON_ERROR_STOP=0 -c "ALTER USER receiptvault WITH PASSWORD '${DB_PASS}';"
runuser -u postgres -- psql -v ON_ERROR_STOP=0 -c "CREATE DATABASE receiptvault OWNER receiptvault;" || true
runuser -u postgres -- psql -d receiptvault -c "GRANT ALL ON SCHEMA public TO receiptvault; ALTER DATABASE receiptvault OWNER TO receiptvault;"

export PATH="/usr/local/bin:/usr/bin:$PATH"
log "Installing Python application"
cd "$APP_ROOT/backend"
runuser -u receiptvault -- env PATH="$PATH" uv sync --frozen --no-dev || runuser -u receiptvault -- env PATH="$PATH" uv sync --no-dev

log "Building web UI"
cd "$APP_ROOT/frontend"
if [[ -f package-lock.json ]]; then
  runuser -u receiptvault -- env PATH="$PATH" npm ci
else
  runuser -u receiptvault -- env PATH="$PATH" npm install
fi
runuser -u receiptvault -- env PATH="$PATH" npm run build

if [[ -n "${RECEIPTVAULT_STATIC_CIDR:-}" && -f "$APP_ROOT/deploy/guest-network.sh" ]]; then
  log "Applying static address ${RECEIPTVAULT_STATIC_CIDR}"
  RV_CIDR="$RECEIPTVAULT_STATIC_CIDR" RV_GATEWAY="${RECEIPTVAULT_GATEWAY:-}" \
    RV_DNS="${RECEIPTVAULT_DNS:-1.1.1.1}" bash "$APP_ROOT/deploy/guest-network.sh"
fi

log "Installing systemd units (Caddy is not used on the LAN — it only showed a welcome page)"
install -m 0755 "$APP_ROOT/deploy/run-api.sh" "$APP_ROOT/deploy/run-api.sh"
install -m 0644 "$APP_ROOT/deploy/systemd/receiptvault.service" /etc/systemd/system/receiptvault.service
install -m 0644 "$APP_ROOT/deploy/systemd/receiptvault-worker.service" /etc/systemd/system/receiptvault-worker.service
LAN_PORT="${RECEIPTVAULT_LAN_PORT:-8082}"
chmod -R a+rX "$APP_ROOT/frontend/dist" || true
ln -sfn "$APP_ROOT/backend/.venv" "$APP_ROOT/.venv"
ln -sfn "$APP_ROOT/backend/.venv/bin/receiptvault" /usr/local/bin/receiptvault
systemctl disable --now caddy >/dev/null 2>&1 || true
systemctl mask caddy >/dev/null 2>&1 || true
systemctl daemon-reload
systemctl enable --now receiptvault receiptvault-worker

log "Waiting for health check on port ${LAN_PORT}"
ok=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${LAN_PORT}/health/live" >/dev/null; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "Health check failed. See journalctl -u receiptvault"
  journalctl -u receiptvault -n 80 --no-pager || true
  exit 1
fi

date -u +%FT%TZ > "$APP_ROOT/.installed"
chown receiptvault:receiptvault "$APP_ROOT/.installed"
log "Bootstrap complete"
echo "LIVE_OK"
