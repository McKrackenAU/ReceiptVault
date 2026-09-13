#!/usr/bin/env bash
# Run as root on the Proxmox HOST. One line (safe for noVNC):
#
#   wget --no-cache -O /root/update-receiptvault.sh https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/update-from-host.sh && bash /root/update-receiptvault.sh
#
# Downloads the tree on the HOST (which can reach GitHub), then copies it
# into the LXC. The guest often cannot git-pull and sometimes cannot curl GitHub.
echo "ReceiptVault 1.4.0 — host download, then unpack in the LXC"
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8

if [[ ${EUID} -ne 0 ]] || ! command -v pct >/dev/null; then
  echo "Run as root on the Proxmox host (the shell that has pct)."
  exit 1
fi

find_ct() {
  local id
  [[ -n "${1:-}" ]] && echo "$1" && return 0
  while read -r id name; do
    [[ "$name" == *receiptvault* ]] && echo "$id" && return 0
  done < <(pct list | awk 'NR>1 {print $1, $3}')
  while read -r id; do
    pct exec "$id" -- test -d /opt/receiptvault 2>/dev/null && echo "$id" && return 0
  done < <(pct list | awk 'NR>1 {print $1}')
  return 1
}

CTID="$(find_ct "${1:-}" || true)"
if [[ -z "$CTID" ]]; then
  echo "No ReceiptVault CT found."
  pct list
  exit 1
fi

TGZ=/tmp/receiptvault-main.tgz
echo "Downloading source on the Proxmox host"
wget --no-cache -O "$TGZ" https://github.com/McKrackenAU/ReceiptVault/archive/refs/heads/main.tar.gz
if ! gzip -t "$TGZ" 2>/dev/null; then
  echo "Download was not a gzip archive. First bytes:"
  head -c 200 "$TGZ"; echo
  exit 1
fi

echo "Copying archive into CT ${CTID}"
pct push "$CTID" "$TGZ" /tmp/receiptvault-main.tgz

echo "Unpacking and rebuilding UI"
pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 bash -s <<'EOS'
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:$PATH"
APP=/opt/receiptvault
if [[ ! -d "$APP/backend" ]]; then
  echo "Missing $APP"
  exit 1
fi
rm -rf /tmp/ReceiptVault-main
tar -xzf /tmp/receiptvault-main.tgz -C /tmp
if [[ ! -d /tmp/ReceiptVault-main/backend ]]; then
  echo "Unexpected archive layout:"; ls /tmp; exit 1
fi
cp -a /tmp/ReceiptVault-main/. "$APP/"
rm -rf /tmp/ReceiptVault-main /tmp/receiptvault-main.tgz
id receiptvault >/dev/null 2>&1 && chown -R receiptvault:receiptvault "$APP/frontend" "$APP/backend/app" "$APP/deploy" || true
cd "$APP/frontend"
if ! command -v npm >/dev/null; then
  echo "npm is missing inside the LXC"
  exit 1
fi
npm install --omit=optional
npx vite build
chmod -R a+rX "$APP/frontend/dist"
if [[ ! -f "$APP/frontend/dist/index.html" ]]; then
  echo "UI build did not produce frontend/dist/index.html"
  exit 1
fi
ENV=/etc/receiptvault/receiptvault.env
if [[ -f "$ENV" ]]; then
  grep -q '^RECEIPTVAULT_APP_VERSION=' "$ENV" && sed -i 's|^RECEIPTVAULT_APP_VERSION=.*|RECEIPTVAULT_APP_VERSION=1.4.0|' "$ENV" || echo 'RECEIPTVAULT_APP_VERSION=1.4.0' >>"$ENV"
fi
systemctl restart receiptvault
ok=0
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1/health/live >/dev/null 2>&1 && ok=1 && break
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  journalctl -u receiptvault -n 40 --no-pager || true
  exit 1
fi
echo UPDATED
EOS

echo "Open http://192.168.13.13/ and hard-refresh (Ctrl+Shift+R). Settings must show 1.4.0."
