#!/usr/bin/env bash
# ReceiptVault Proxmox helper-script installer.
# Download, read, then run as root on a Proxmox VE host. Do not pipe credentials into this command.
set -euo pipefail

VERSION="1.0.0"
PROJECT_URL="https://github.com/example/receiptvault"
LOG="/var/tmp/receiptvault-install.log"
redact() { sed -E 's/(PASSWORD|SECRET|TOKEN|KEY|MASTER)=.*/\1=[redacted]/g'; }
log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG" | redact >/dev/null; echo "$*"; }

need_root() {
  if [[ ${EUID} -ne 0 ]]; then
    echo "Run as root in the Proxmox shell."; exit 1
  fi
}

need_proxmox() {
  if [[ ! -f /etc/pve/.version ]] && ! command -v pct >/dev/null; then
    echo "This installer targets Proxmox VE."; exit 1
  fi
}

dialog_bin() {
  if command -v whiptail >/dev/null; then echo whiptail
  elif command -v dialog >/dev/null; then echo dialog
  else
    apt-get update -y && apt-get install -y whiptail
    echo whiptail
  fi
}

UI=$(dialog_bin)
ask() { $UI --title "ReceiptVault" --inputbox "$1" 10 70 "$2" 3>&1 1>&2 2>&3; }
yesno() { $UI --title "ReceiptVault" --yesno "$1" 12 70; }
menu() { $UI --title "ReceiptVault" --menu "$1" 20 78 10 "${@:2}" 3>&1 1>&2 2>&3; }
msg() { $UI --title "ReceiptVault" --msgbox "$1" 14 78; }
gauge() { $UI --title "ReceiptVault" --gauge "$1" 8 70 "$2"; }

need_root
need_proxmox

$UI --title "ReceiptVault $VERSION" --msgbox "Welcome to ReceiptVault $VERSION\n\nProject: $PROJECT_URL\n\nThis will create or manage a Debian 13 LXC, install PostgreSQL, Redis, Caddy, OCR tools, and ReceiptVault.\n\nSafer sequence:\n  1. Download this script\n  2. Read it\n  3. bash install-receiptvault.sh\n\nNever paste mailbox passwords or tokens into the shell command." 18 78

MODE=$(menu "Install type" default "Recommended unprivileged LXC" advanced "Tune CPU/RAM/network" repair "Repair/update existing" uninstall "Remove a recognised CT")
if [[ "$MODE" == "repair" || "$MODE" == "uninstall" ]]; then
  CTID=$(ask "Existing ReceiptVault CTID" "200")
  if [[ "$MODE" == "uninstall" ]]; then
    yesno "Destroy CT $CTID? Evidence bind mounts are not deleted." || exit 0
    pct stop "$CTID" || true
    pct destroy "$CTID"
    msg "Container removed. Host evidence directories were left in place."
    exit 0
  fi
  pct exec "$CTID" -- bash -lc 'systemctl restart receiptvault receiptvault-worker caddy'
  msg "Repair restart issued for CT $CTID"
  exit 0
fi

CTID=$(ask "Container ID (must be unused)" "200")
if pct status "$CTID" >/dev/null 2>&1; then
  msg "CTID $CTID is already in use. Refusing to overwrite."; exit 1
fi
HOSTNAME=$(ask "Hostname" "receiptvault")
STORAGE=$(ask "Storage target" "local-lvm")
DISK=$(ask "Root disk size (GB)" "32")
if [[ "$MODE" == "advanced" ]]; then
  CORES=$(ask "vCPU" "4")
  MEMORY=$(ask "RAM (MB)" "8192")
  BRIDGE=$(ask "Bridge" "vmbr0")
  NETMODE=$(menu "IPv4" dhcp "DHCP" static "Static")
  IP=""
  GW=""
  DNS="1.1.1.1"
  if [[ "$NETMODE" == "static" ]]; then
    IP=$(ask "CIDR e.g. 192.168.1.50/24" "")
    GW=$(ask "Gateway" "")
    DNS=$(ask "DNS" "1.1.1.1")
  fi
  UNPRIV=$(yesno "Unprivileged container? (recommended)" && echo 1 || echo 0)
else
  CORES=4; MEMORY=8192; BRIDGE=vmbr0; NETMODE=dhcp; IP=""; GW=""; DNS="1.1.1.1"; UNPRIV=1
fi
EVIDENCE=$(menu "Evidence storage" root "Inside LXC root disk" bindnew "New host directory bind mount" bindexist "Existing host/NFS path")
EVPATH="/var/lib/receiptvault/evidence"
if [[ "$EVIDENCE" != "root" ]]; then
  EVPATH=$(ask "Host evidence path" "$EVPATH")
fi
APPPORT=$(ask "Published application port on LAN" "8080")
CF=$(menu "Cloudflare" skip "Skip (LAN only)" existing "I already have a tunnel" managed "Install cloudflared in the LXC")

SUMMARY="CTID=$CTID host=$HOSTNAME storage=$STORAGE disk=${DISK}G cpu=$CORES ram=${MEMORY}MB bridge=$BRIDGE net=$NETMODE evidence=$EVIDENCE:$EVPATH port=$APPPORT cf=$CF unprivileged=$UNPRIV"
yesno "Create container with:\n$SUMMARY\n\nContinue?" || exit 0

{
  echo 10
  if ! pveam list local | grep -q debian-13; then
    pveam update || true
    pveam download local debian-13-standard_13.0-1_amd64.tar.zst || log "Select an existing Debian 13 template if download failed"
  fi
  echo 25
  NET="name=eth0,bridge=$BRIDGE,ip=dhcp"
  if [[ "$NETMODE" == "static" ]]; then
    NET="name=eth0,bridge=$BRIDGE,ip=$IP,gw=$GW"
  fi
  pct create "$CTID" "local:vztmpl/debian-13-standard_13.0-1_amd64.tar.zst" \
    --hostname "$HOSTNAME" --cores "$CORES" --memory "$MEMORY" --rootfs "$STORAGE:${DISK}" \
    --net0 "$NET" --unprivileged "$UNPRIV" --features nesting=0,keyctl=0 --ostype debian \
    --onboot 1 --start 0 || {
      log "pct create failed"; exit 1
    }
  echo 40
  if [[ "$EVIDENCE" != "root" ]]; then
    mkdir -p "$EVPATH"
    echo "Bind-mounting $EVPATH. Unprivileged LXCs map container UID 1000 to a mapped host UID; chown the host path to the mapped owner after first boot if writes fail."
    echo "mp0: $EVPATH,mp=/var/lib/receiptvault/evidence" >> "/etc/pve/lxc/${CTID}.conf"
  fi
  pct start "$CTID"
  echo 55
  pct exec "$CTID" -- bash -lc "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip postgresql postgresql-contrib redis-server caddy tesseract-ocr ghostscript qpdf libmagic1 poppler-utils curl git"
  echo 70
  MASTER=$(python3 - <<'PY'
import secrets; print(secrets.token_urlsafe(48))
PY
)
  pct exec "$CTID" -- bash -lc "useradd --system --home /opt/receiptvault --shell /usr/sbin/nologin receiptvault || true
mkdir -p /opt/receiptvault /etc/receiptvault /var/lib/receiptvault/{evidence,derived,staging,backups}
chown -R receiptvault:receiptvault /opt/receiptvault /var/lib/receiptvault
install -d -m 0700 /etc/receiptvault"
  pct exec "$CTID" -- bash -lc "cat >/etc/receiptvault/receiptvault.env <<EOF
RECEIPTVAULT_ENV=production
RECEIPTVAULT_PUBLIC_URL=http://127.0.0.1:${APPPORT}
RECEIPTVAULT_MASTER_KEY=${MASTER}
RECEIPTVAULT_DATABASE_URL=postgresql+psycopg://receiptvault:receiptvault@127.0.0.1:5432/receiptvault
RECEIPTVAULT_REDIS_URL=redis://127.0.0.1:6379/0
RECEIPTVAULT_EVIDENCE_ROOT=/var/lib/receiptvault/evidence
RECEIPTVAULT_DERIVED_ROOT=/var/lib/receiptvault/derived
RECEIPTVAULT_STAGING_ROOT=/var/lib/receiptvault/staging
RECEIPTVAULT_BACKUP_ROOT=/var/lib/receiptvault/backups
RECEIPTVAULT_COOKIE_SECURE=false
RECEIPTVAULT_GRAPH_MOCK=false
EOF
chmod 600 /etc/receiptvault/receiptvault.env"
  echo 85
  pct exec "$CTID" -- bash -lc "sudo -u postgres psql -c \"CREATE USER receiptvault PASSWORD 'receiptvault';\" || true
sudo -u postgres createdb -O receiptvault receiptvault || true
systemctl enable --now postgresql redis-server"
  echo 95
} | gauge "Installing ReceiptVault" 0

if [[ "$CF" == "managed" ]]; then
  TOKEN=$($UI --passwordbox "Paste the Cloudflare tunnel token (not logged)" 10 70 3>&1 1>&2 2>&3)
  pct exec "$CTID" -- bash -lc "curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb && dpkg -i /tmp/cloudflared.deb || true
install -d -m 0700 /etc/cloudflared
printf '%s' '$TOKEN' > /etc/cloudflared/token
chmod 600 /etc/cloudflared/token
cat >/etc/systemd/system/cloudflared.service <<'EOF'
[Unit]
Description=cloudflared
After=network-online.target
[Service]
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate run --token-file /etc/cloudflared/token
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
systemctl enable --now cloudflared"
fi

IPADDR=$(pct exec "$CTID" -- hostname -I | awk '{print $1}')
msg "ReceiptVault LXC $CTID is running.\nLAN: http://${IPADDR}:${APPPORT}\nFirst-run owner setup is at that URL.\nInstall log: $LOG (secrets redacted).\nExisting Cloudflare tunnels should target http://${IPADDR}:8080."
log "Completed CT $CTID ip=$IPADDR"
