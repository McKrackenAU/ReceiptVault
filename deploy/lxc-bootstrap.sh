#!/usr/bin/env bash
# Runs inside the ReceiptVault LXC as root. Do not put secrets on the invoking command line.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/receiptvault}"
ENV_FILE="${ENV_FILE:-/etc/receiptvault/receiptvault.env}"
LOG="${LOG:-/var/log/receiptvault-bootstrap.log}"
mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

redact() { sed -E 's/(PASSWORD|SECRET|TOKEN|KEY|MASTER|REFRESH)=.*/\1=[redacted]/Ig'; }
log() { echo "[$(date -u +%FT%TZ)] $*" | redact; }

if [[ ${EUID} -ne 0 ]]; then
  echo "lxc-bootstrap.sh must run as root inside the container."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
log "Installing runtime packages"
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl git gnupg \
  python3 python3-venv python3-pip python3-dev build-essential \
  postgresql postgresql-contrib redis-server \
  caddy tesseract-ocr tesseract-ocr-eng ghostscript qpdf libmagic1 poppler-utils \
  libpq-dev

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
sudo -u postgres psql -v ON_ERROR_STOP=0 -c "CREATE USER receiptvault LOGIN PASSWORD '${DB_PASS}';" || true
sudo -u postgres psql -v ON_ERROR_STOP=0 -c "ALTER USER receiptvault WITH PASSWORD '${DB_PASS}';"
sudo -u postgres psql -v ON_ERROR_STOP=0 -c "CREATE DATABASE receiptvault OWNER receiptvault;" || true
sudo -u postgres psql -d receiptvault -c "GRANT ALL ON SCHEMA public TO receiptvault; ALTER DATABASE receiptvault OWNER TO receiptvault;"

export PATH="/usr/local/bin:/usr/bin:$PATH"
log "Installing Python application"
cd "$APP_ROOT/backend"
sudo -u receiptvault env PATH="$PATH" uv sync --frozen --no-dev || sudo -u receiptvault env PATH="$PATH" uv sync --no-dev

log "Building web UI"
cd "$APP_ROOT/frontend"
if [[ -f package-lock.json ]]; then
  sudo -u receiptvault env PATH="$PATH" npm ci
else
  sudo -u receiptvault env PATH="$PATH" npm install
fi
sudo -u receiptvault env PATH="$PATH" npm run build

log "Installing systemd units and Caddy"
install -m 0644 "$APP_ROOT/deploy/systemd/receiptvault.service" /etc/systemd/system/receiptvault.service
install -m 0644 "$APP_ROOT/deploy/systemd/receiptvault-worker.service" /etc/systemd/system/receiptvault-worker.service
install -m 0644 "$APP_ROOT/deploy/caddy/Caddyfile" /etc/caddy/Caddyfile
ln -sf "$APP_ROOT/backend/.venv/bin/receiptvault" /usr/local/bin/receiptvault
systemctl daemon-reload
systemctl enable --now caddy receiptvault receiptvault-worker

log "Waiting for health check"
ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8473/health/live >/dev/null; then
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
