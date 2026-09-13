#!/usr/bin/env bash
# Runs INSIDE the ReceiptVault LXC as root.
# Downloads GitHub main as a tarball (this tree is not a git clone) and rebuilds.
echo "ReceiptVault 1.5.1 guest update — started"
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive
export PATH="/usr/local/bin:/usr/bin:$PATH"

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root inside the LXC."
  exit 1
fi

APP=/opt/receiptvault
ENV=/etc/receiptvault/receiptvault.env
TGZ=/tmp/receiptvault-main.tgz
TARBALL_URL="${RECEIPTVAULT_TARBALL_URL:-https://github.com/McKrackenAU/ReceiptVault/archive/refs/heads/main.tar.gz}"

if [[ ! -d "$APP/backend" ]]; then
  echo "Missing $APP/backend — this is not a ReceiptVault CT."
  exit 1
fi

echo "Downloading source from GitHub (IPv4, 40s timeout)"
wget -4 --timeout=40 --tries=3 -nv --no-cache -O "$TGZ" "$TARBALL_URL"
if ! gzip -t "$TGZ" 2>/dev/null; then
  echo "ERROR: download was not a gzip archive. First bytes:"
  head -c 200 "$TGZ"; echo
  exit 1
fi

echo "Unpacking over $APP (venv, evidence, and env file are kept)"
rm -rf /tmp/ReceiptVault-main
tar -xzf "$TGZ" -C /tmp
SRC="$(find /tmp -maxdepth 1 -type d -name 'ReceiptVault-*' | head -n 1)"
if [[ -z "$SRC" || ! -d "$SRC/backend" ]]; then
  echo "ERROR: unexpected archive layout"
  ls /tmp
  exit 1
fi
cp -a "$SRC/backend/." "$APP/backend/"
cp -a "$SRC/frontend/." "$APP/frontend/"
mkdir -p "$APP/deploy"
cp -a "$SRC/deploy/." "$APP/deploy/"
rm -rf "$SRC" "$TGZ"
chmod +x "$APP/deploy/"*.sh "$APP/deploy/run-api.sh" 2>/dev/null || true
id receiptvault >/dev/null 2>&1 && chown -R receiptvault:receiptvault "$APP/frontend" "$APP/backend/app" "$APP/deploy" || true

if [[ -f "$ENV" ]]; then
  grep -q '^RECEIPTVAULT_APP_VERSION=' "$ENV" && sed -i 's|^RECEIPTVAULT_APP_VERSION=.*|RECEIPTVAULT_APP_VERSION=1.5.1|' "$ENV" || echo 'RECEIPTVAULT_APP_VERSION=1.5.1' >>"$ENV"
fi

echo "Building UI"
command -v npm >/dev/null || apt-get install -y -qq npm >/dev/null
cd "$APP/frontend"
if [[ -f package-lock.json ]]; then
  npm ci --omit=optional || npm install --omit=optional
else
  npm install --omit=optional
fi
npx vite build
chmod -R a+rX "$APP/frontend/dist"
if [[ ! -f "$APP/frontend/dist/index.html" ]]; then
  echo "ERROR: UI build did not produce frontend/dist/index.html"
  exit 1
fi

if [[ -x "$APP/backend/.venv/bin/uv" ]] || command -v uv >/dev/null; then
  echo "Syncing Python env"
  cd "$APP/backend"
  if [[ -x .venv/bin/uv ]]; then
    .venv/bin/uv sync --frozen --no-dev || .venv/bin/uv sync --no-dev
  elif command -v uv >/dev/null; then
    uv sync --frozen --no-dev || uv sync --no-dev
  fi
fi

echo "Restarting ReceiptVault"
systemctl restart receiptvault || true
systemctl restart receiptvault-worker || true
ok=0
for _ in $(seq 1 40); do
  body="$(curl -fsS http://127.0.0.1/health/live 2>/dev/null || true)"
  if [[ "$body" == *ok* ]]; then
    echo "health: $body"
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "Service did not become healthy."
  journalctl -u receiptvault -n 40 --no-pager || true
  exit 1
fi
echo "UPDATED to 1.5.1"
echo "Hard-refresh the LXC address in the browser — Settings must show 1.5.1"
