#!/usr/bin/env bash
# Remove Caddy completely. Debian's package owns :80 with a welcome page
# the moment it is installed. ReceiptVault binds port 80 itself.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

systemctl disable --now caddy.service caddy.socket >/dev/null 2>&1 || true
systemctl mask caddy.service caddy.socket >/dev/null 2>&1 || true
pkill -9 caddy >/dev/null 2>&1 || true
# Free :80 even if something other than systemd started Caddy.
if command -v fuser >/dev/null; then
  fuser -k 80/tcp >/dev/null 2>&1 || true
fi
ss -lntp 2>/dev/null | grep -q ':80 ' && fuser -k 80/tcp >/dev/null 2>&1 || true

apt-get purge -y caddy >/dev/null 2>&1 || dpkg --purge caddy >/dev/null 2>&1 || true
apt-get autoremove -y >/dev/null 2>&1 || true
rm -rf /etc/caddy /usr/share/caddy /var/lib/caddy /etc/systemd/system/caddy.service.d
systemctl daemon-reload >/dev/null 2>&1 || true

# Stop apt from pulling Caddy back in as a recommend.
apt-mark hold caddy >/dev/null 2>&1 || true

if command -v caddy >/dev/null 2>&1 || [[ -x /usr/bin/caddy ]]; then
  rm -f /usr/bin/caddy /usr/local/bin/caddy
fi

echo "CADDY_PURGED"
