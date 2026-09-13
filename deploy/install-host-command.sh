#!/usr/bin/env bash
# Installs a short typed command on the Proxmox HOST: receiptvault-update
set -euo pipefail
if [[ ${EUID} -ne 0 ]] || ! command -v pct >/dev/null; then
  echo "Run as root on the Proxmox host."
  exit 1
fi
cat >/usr/local/sbin/receiptvault-update <<'EOF'
#!/bin/bash
echo "ReceiptVault host update"
set -euo pipefail
if [[ ${EUID} -ne 0 ]] || ! command -v pct >/dev/null; then
  echo "Run as root on the Proxmox host (the shell that has pct)."
  exit 1
fi
command -v git >/dev/null || apt-get install -y -qq git
if [[ -d /root/ReceiptVault/.git ]]; then
  echo "Updating /root/ReceiptVault"
  git -C /root/ReceiptVault fetch --depth 1 origin main
  git -C /root/ReceiptVault reset --hard origin/main
else
  echo "Cloning https://github.com/McKrackenAU/ReceiptVault.git"
  rm -rf /root/ReceiptVault
  git clone --depth 1 https://github.com/McKrackenAU/ReceiptVault.git /root/ReceiptVault
fi
exec bash /root/ReceiptVault/deploy/fix-from-host.sh "$@"
EOF
chmod 0755 /usr/local/sbin/receiptvault-update
echo "Installed. Next time type: receiptvault-update"
