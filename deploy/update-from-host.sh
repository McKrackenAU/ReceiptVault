#!/usr/bin/env bash
# Run as root on the Proxmox HOST. One line — do not split it.
#
#   wget --no-cache -O /root/update-receiptvault.sh https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/update-from-host.sh
#   bash /root/update-receiptvault.sh
#
# The LXC often has no .git (tar install). This unpacks GitHub main and rebuilds the UI.
echo "ReceiptVault update 1.3.1 — unpack GitHub main (no git required)"
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

echo "Updating CT ${CTID}"
pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 bash -s <<'EOS'
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:$PATH"
APP=/opt/receiptvault
if [[ ! -d "$APP/backend" ]]; then
  echo "Missing $APP"
  exit 1
fi
curl -fsSL https://github.com/McKrackenAU/ReceiptVault/archive/refs/heads/main.tar.gz -o /tmp/receiptvault-main.tgz
rm -rf /tmp/ReceiptVault-main
tar -xzf /tmp/receiptvault-main.tgz -C /tmp
cp -a /tmp/ReceiptVault-main/. "$APP/"
rm -rf /tmp/ReceiptVault-main /tmp/receiptvault-main.tgz
chown -R receiptvault:receiptvault "$APP" || true
cd "$APP/frontend"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
npm run build
chmod -R a+rX "$APP/frontend/dist"
systemctl restart receiptvault
sleep 2
curl -fsS http://127.0.0.1/health/live
echo
echo UPDATED
EOS

echo "Open http://192.168.13.13/ and hard-refresh (Ctrl+Shift+R)."
