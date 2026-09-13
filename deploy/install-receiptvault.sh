#!/usr/bin/env bash
# ReceiptVault — Proxmox helper-script installer
# Safe sequence (recommended):
#   wget -O /root/install-receiptvault.sh https://raw.githubusercontent.com/<user>/receiptvault/main/deploy/install-receiptvault.sh
#   less /root/install-receiptvault.sh
#   bash /root/install-receiptvault.sh
#
# Convenient one-liner (inspect the URL first; never put tokens on this line):
#   bash -c "$(wget -qLO - https://raw.githubusercontent.com/<user>/receiptvault/main/deploy/install-receiptvault.sh)"
#
# Override the Git source if needed:
#   RECEIPTVAULT_REPO=https://github.com/<user>/receiptvault.git bash /root/install-receiptvault.sh
set -euo pipefail

VERSION="1.0.0"
APP="ReceiptVault"
# Change this after you publish the GitHub repo, or pass RECEIPTVAULT_REPO=
REPO_URL="${RECEIPTVAULT_REPO:-https://github.com/williamdornay/receiptvault.git}"
REPO_REF="${RECEIPTVAULT_REF:-main}"
LOG="/var/tmp/receiptvault-install.log"
MARKER_KEY="receiptvault.installed"

YW=$'\033[33m'
GN=$'\033[1;92m'
RD=$'\033[01;31m'
BL=$'\033[36m'
CL=$'\033[m'

redact() { sed -E 's/(PASSWORD|SECRET|TOKEN|KEY|MASTER|REFRESH)=.*/\1=[redacted]/Ig'; }
log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG" | redact >/dev/null; echo -e "$*"; }

header() {
  clear
  echo -e "${GN}"
  cat <<'EOF'
  ____                _       _ __     __            _ _
 |  _ \ ___  ___ ___(_)_ __ | |\ \   / /_ _ _   _| | |_
 | |_) / _ \/ __/ _ \ | '_ \| __\ \ / / _` | | | | | __|
 |  _ <  __/ (_|  __/ | |_) | |_ \ V / (_| | |_| | | |_
 |_| \_\___|\___\___|_| .__/ \__| \_/ \__,_|\__,_|_|\__|
                      |_|
EOF
  echo -e "${CL}${BL}  ${APP} ${VERSION} — Proxmox LXC helper${CL}"
  echo
}

need_root() {
  if [[ ${EUID} -ne 0 ]]; then
    echo -e "${RD}Run this as root in the Proxmox VE shell.${CL}"
    exit 1
  fi
}

need_proxmox() {
  if ! command -v pct >/dev/null || ! command -v pveam >/dev/null; then
    echo -e "${RD}This installer must run on a Proxmox VE host (pct/pveam missing).${CL}"
    exit 1
  fi
}

dialog_bin() {
  if command -v whiptail >/dev/null; then echo whiptail
  elif command -v dialog >/dev/null; then echo dialog
  else
    apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y whiptail
    echo whiptail
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || true)"
LOCAL_SOURCE=""
if [[ -n "${SCRIPT_DIR}" && -f "${SCRIPT_DIR}/lxc-bootstrap.sh" && -d "${SCRIPT_DIR}/../backend" ]]; then
  LOCAL_SOURCE="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

need_root
need_proxmox
mkdir -p "$(dirname "$LOG")"
touch "$LOG"
header

UI="$(dialog_bin)"
ask() { $UI --title "$APP" --inputbox "$1" 10 74 "$2" 3>&1 1>&2 2>&3; }
yesno() { $UI --title "$APP" --yesno "$1" 13 74; }
menu() { $UI --title "$APP" --menu "$1" 20 78 12 "${@:2}" 3>&1 1>&2 2>&3; }
msg() { $UI --title "$APP" --msgbox "$1" 16 78; }
gauge() { $UI --title "$APP" --gauge "$1" 10 74 "$2"; }

$UI --title "$APP $VERSION" --msgbox "This helper creates or manages an unprivileged Debian 13 LXC and installs ${APP}.\n\nIt will install PostgreSQL, Redis, Caddy, OCR tools, and the application.\n\nSafer sequence:\n  1. wget the script\n  2. read it (less)\n  3. bash the file\n\nNever paste mailbox passwords or Cloudflare tokens on the wget/curl line.\n\nSource: ${REPO_URL}" 20 78

MODE="$(menu "What do you want to do?" \
  default "Default install (recommended)" \
  advanced "Advanced install (CPU, RAM, network, repo URL)" \
  repair "Repair / restart a recognised ReceiptVault CT" \
  update "Update application in a recognised CT" \
  backup "Create a backup inside a recognised CT" \
  restore "Restore (dry-run first) inside a recognised CT" \
  uninstall "Remove a recognised ReceiptVault CT")"

recognised() {
  local id="$1"
  pct exec "$id" -- test -f /opt/receiptvault/.installed
}

if [[ "$MODE" == "repair" || "$MODE" == "update" || "$MODE" == "backup" || "$MODE" == "restore" || "$MODE" == "uninstall" ]]; then
  CTID="$(ask "ReceiptVault CTID" "200")"
  if ! pct status "$CTID" >/dev/null 2>&1; then
    msg "CT $CTID does not exist."; exit 1
  fi
  if ! recognised "$CTID"; then
    yesno "CT $CTID does not have a ReceiptVault install marker. Continue anyway?" || exit 0
  fi
  case "$MODE" in
    uninstall)
      yesno "Destroy CT $CTID? Host evidence bind mounts are NOT deleted." || exit 0
      pct stop "$CTID" || true
      pct destroy "$CTID"
      msg "Container $CTID removed. Evidence directories on the host were left in place."
      exit 0
      ;;
    repair)
      pct exec "$CTID" -- bash -lc 'systemctl restart postgresql redis-server caddy receiptvault receiptvault-worker'
      pct exec "$CTID" -- curl -fsS http://127.0.0.1:8473/health/live >/dev/null
      msg "Repair restart completed for CT $CTID."
      exit 0
      ;;
    update)
      PRE="$(pct exec "$CTID" -- git -C /opt/receiptvault rev-parse HEAD)"
      pct exec "$CTID" -- bash -lc "cd /opt/receiptvault && git fetch --tags origin && git checkout ${REPO_REF} && git pull --ff-only origin ${REPO_REF}"
      if ! pct exec "$CTID" -- bash /opt/receiptvault/deploy/lxc-bootstrap.sh; then
        pct exec "$CTID" -- git -C /opt/receiptvault checkout "$PRE"
        msg "Update failed health/bootstrap. Application tree rolled back to ${PRE}."
        exit 1
      fi
      msg "Updated CT $CTID to ${REPO_REF}."
      exit 0
      ;;
    backup)
      pct exec "$CTID" -- bash -lc 'receiptvault backup --include-evidence'
      msg "Backup requested inside CT $CTID. See /var/lib/receiptvault/backups"
      exit 0
      ;;
    restore)
      RPATH="$(ask "Backup path inside the CT" "/var/lib/receiptvault/backups")"
      pct exec "$CTID" -- receiptvault restore "$RPATH" --dry-run
      yesno "Dry-run finished. Apply restore? Type-through confirmation is still required by the tool." || exit 0
      pct exec "$CTID" -- receiptvault restore "$RPATH" --no-dry-run --confirm
      exit 0
      ;;
  esac
fi

CTID="$(ask "Container ID (must be unused)" "200")"
if pct status "$CTID" >/dev/null 2>&1; then
  msg "CTID $CTID is already in use. Refusing to overwrite an existing container."
  exit 1
fi
HOSTNAME="$(ask "Hostname" "receiptvault")"
STORAGE="$(ask "Storage target" "local-lvm")"
DISK="$(ask "Root disk size (GB)" "32")"
if [[ "$MODE" == "advanced" ]]; then
  CORES="$(ask "vCPU" "4")"
  MEMORY="$(ask "RAM (MB)" "8192")"
  BRIDGE="$(ask "Bridge" "vmbr0")"
  NETMODE="$(menu "IPv4" dhcp "DHCP" static "Static IPv4")"
  IP=""; GW=""; DNS="1.1.1.1"
  if [[ "$NETMODE" == "static" ]]; then
    IP="$(ask "IPv4 CIDR  e.g. 192.168.1.50/24" "")"
    GW="$(ask "Gateway" "")"
    DNS="$(ask "DNS" "1.1.1.1")"
  fi
  if yesno "Unprivileged container? (recommended: Yes)"; then UNPRIV=1; else UNPRIV=0; fi
  REPO_URL="$(ask "Git clone URL for ReceiptVault" "$REPO_URL")"
  REPO_REF="$(ask "Git ref (branch or tag)" "$REPO_REF")"
else
  CORES=4; MEMORY=8192; BRIDGE=vmbr0; NETMODE=dhcp; IP=""; GW=""; DNS="1.1.1.1"; UNPRIV=1
fi

EVIDENCE="$(menu "Evidence storage" \
  root "Store on the LXC root disk" \
  bindnew "Create a new host directory and bind-mount it" \
  bindexist "Bind-mount an existing host or NFS path")"
EVPATH="/var/lib/receiptvault/evidence"
if [[ "$EVIDENCE" != "root" ]]; then
  EVPATH="$(ask "Host evidence path" "$EVPATH")"
fi
APPPORT="$(ask "LAN port published via Caddy" "8080")"
CF="$(menu "Cloudflare Tunnel" \
  skip "LAN only (no public hostname)" \
  existing "I already have a tunnel — show origin settings" \
  managed "Install cloudflared in the LXC (token entered here, not logged)")"

SOURCE_NOTE="git ${REPO_URL}#${REPO_REF}"
[[ -n "$LOCAL_SOURCE" ]] && SOURCE_NOTE="local tree ${LOCAL_SOURCE} (fallback git ${REPO_URL})"

SUMMARY="CTID=${CTID}\nHostname=${HOSTNAME}\nStorage=${STORAGE}  Disk=${DISK}G  CPU=${CORES}  RAM=${MEMORY}MB\nBridge=${BRIDGE}  IPv4=${NETMODE} ${IP}\nUnprivileged=${UNPRIV}\nEvidence=${EVIDENCE} ${EVPATH}\nPort=${APPPORT}  Cloudflare=${CF}\nSource=${SOURCE_NOTE}"
yesno "Create this container?\n\n${SUMMARY}" || exit 0

rand() { python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}
MASTER="$(rand)"
DBPASS="$(rand)"

resolve_template() {
  local existing avail
  existing="$(pveam list local 2>/dev/null | awk '/debian-13/ && /amd64/ {print $1; exit}')"
  if [[ -n "$existing" ]]; then
    echo "$existing"
    return 0
  fi
  pveam update >/dev/null || true
  avail="$(pveam available --section system 2>/dev/null | awk '/debian-13-standard/ && /amd64/ {print $2; exit}')"
  if [[ -z "$avail" ]]; then
    echo ""
    return 1
  fi
  pveam download local "$avail" >/dev/null
  pveam list local | awk '/debian-13/ && /amd64/ {print $1; exit}'
}

(
  echo 8
  TEMPLATE="$(resolve_template || true)"
  if [[ -z "${TEMPLATE:-}" ]]; then
    echo "Debian 13 template not found. Select one with: pveam available --section system" | tee -a "$LOG"
    exit 1
  fi
  echo 18
  NET="name=eth0,bridge=${BRIDGE},ip=dhcp"
  if [[ "$NETMODE" == "static" ]]; then
    NET="name=eth0,bridge=${BRIDGE},ip=${IP},gw=${GW}"
  fi
  pct create "$CTID" "$TEMPLATE" \
    --hostname "$HOSTNAME" \
    --cores "$CORES" \
    --memory "$MEMORY" \
    --rootfs "${STORAGE}:${DISK}" \
    --net0 "$NET" \
    --unprivileged "$UNPRIV" \
    --features nesting=0 \
    --ostype debian \
    --onboot 1 \
    --start 0
  if [[ -n "$DNS" && "$NETMODE" == "static" ]]; then
    pct set "$CTID" --nameserver "$DNS" || true
  fi
  echo 32
  if [[ "$EVIDENCE" != "root" ]]; then
    mkdir -p "$EVPATH"
    echo "Bind-mounting ${EVPATH}. Unprivileged LXCs map container UIDs; if writes fail, chown the host path to the mapped UID of receiptvault (often 100000+)." | tee -a "$LOG"
    pct set "$CTID" --mp0 "${EVPATH},mp=/var/lib/receiptvault/evidence"
  fi
  echo 40
  pct start "$CTID"
  for _ in $(seq 1 40); do
    if pct exec "$CTID" -- true >/dev/null 2>&1; then break; fi
    sleep 1
  done
  echo 48
  pct exec "$CTID" -- bash -lc 'apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl git'
  echo 58
  pct exec "$CTID" -- bash -lc 'mkdir -p /opt/receiptvault /etc/receiptvault'
  if [[ -n "$LOCAL_SOURCE" ]]; then
    tar -C "$LOCAL_SOURCE" --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='backend/.venv' --exclude='var' --exclude='frontend/node_modules' -cf - . \
      | pct exec "$CTID" -- tar -C /opt/receiptvault -xf -
  else
    pct exec "$CTID" -- bash -lc "git clone --depth 1 --branch '${REPO_REF}' '${REPO_URL}' /opt/receiptvault"
  fi
  echo 70
  pct exec "$CTID" -- tee /etc/receiptvault/receiptvault.env >/dev/null <<ENVEOF
RECEIPTVAULT_ENV=production
RECEIPTVAULT_PUBLIC_URL=http://127.0.0.1:${APPPORT}
RECEIPTVAULT_API_HOST=127.0.0.1
RECEIPTVAULT_API_PORT=8473
RECEIPTVAULT_TIMEZONE=Australia/Melbourne
RECEIPTVAULT_MASTER_KEY=${MASTER}
RECEIPTVAULT_DATABASE_URL=postgresql+psycopg://receiptvault:${DBPASS}@127.0.0.1:5432/receiptvault
RECEIPTVAULT_REDIS_URL=redis://127.0.0.1:6379/0
RECEIPTVAULT_EVIDENCE_ROOT=/var/lib/receiptvault/evidence
RECEIPTVAULT_DERIVED_ROOT=/var/lib/receiptvault/derived
RECEIPTVAULT_STAGING_ROOT=/var/lib/receiptvault/staging
RECEIPTVAULT_BACKUP_ROOT=/var/lib/receiptvault/backups
RECEIPTVAULT_COOKIE_SECURE=false
RECEIPTVAULT_GRAPH_MOCK=false
RECEIPTVAULT_MS_TENANT=common
ENVEOF
  pct exec "$CTID" -- chmod 600 /etc/receiptvault/receiptvault.env
  echo 78
  pct exec "$CTID" -- bash /opt/receiptvault/deploy/lxc-bootstrap.sh
  echo 92
  IPADDR="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
  pct exec "$CTID" -- bash -lc "sed -i 's|^RECEIPTVAULT_PUBLIC_URL=.*|RECEIPTVAULT_PUBLIC_URL=http://${IPADDR}:${APPPORT}|' /etc/receiptvault/receiptvault.env"
  pct exec "$CTID" -- systemctl restart receiptvault
  pct exec "$CTID" -- bash -lc "echo ${MARKER_KEY}=${VERSION} > /opt/receiptvault/.installed"
  echo 100
) | gauge "Installing ${APP}" 0

IPADDR="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
ORIGIN="http://${IPADDR}:8080"

if [[ "$CF" == "managed" ]]; then
  TOKEN="$($UI --passwordbox "Paste the Cloudflare tunnel token. It is written to a root-only file and is not appended to the install log." 12 74 3>&1 1>&2 2>&3 || true)"
  if [[ -n "${TOKEN}" ]]; then
    pct exec "$CTID" -- bash -lc "curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb && dpkg -i /tmp/cloudflared.deb
install -d -m 0700 /etc/cloudflared"
    printf '%s' "$TOKEN" | pct exec "$CTID" -- tee /etc/cloudflared/token >/dev/null
    pct exec "$CTID" -- bash -lc "chmod 600 /etc/cloudflared/token
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
    log "cloudflared installed (token not logged)"
  fi
fi

FINAL="ReceiptVault CT ${CTID} is ready.\n\nLAN setup URL:\n  http://${IPADDR}:${APPPORT}\n\nCreate the owner account there. Then add Entra app credentials, connect three inboxes, pick audit years, and start the first scan.\n\nExisting Cloudflare Tunnel origin:\n  ${ORIGIN}\n\nInstall log (secrets redacted): ${LOG}\n\nRe-run this helper and choose Update / Repair / Backup / Uninstall for this CT."
msg "$FINAL"
log "Completed CT $CTID ip=$IPADDR port=$APPPORT"
echo -e "${GN}Done.${CL} Open ${BL}http://${IPADDR}:${APPPORT}${CL}"
