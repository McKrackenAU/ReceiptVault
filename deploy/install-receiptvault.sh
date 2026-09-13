#!/usr/bin/env bash
# ReceiptVault — Proxmox helper-script installer
# Safe sequence (recommended):
#   wget -O /root/install-receiptvault.sh https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/install-receiptvault.sh
#   less /root/install-receiptvault.sh
#   bash /root/install-receiptvault.sh
#
# Convenient one-liner (inspect the URL first; never put tokens on this line):
#   bash -c "$(wget -qLO - https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/install-receiptvault.sh)"
#
# Override the Git source if needed:
#   RECEIPTVAULT_REPO=https://github.com/McKrackenAU/ReceiptVault.git bash /root/install-receiptvault.sh
set -euo pipefail

VERSION="1.3.0"
APP="ReceiptVault"
REPO_URL="${RECEIPTVAULT_REPO:-https://github.com/McKrackenAU/ReceiptVault.git}"
REPO_REF="${RECEIPTVAULT_REF:-main}"
LOG="/var/tmp/receiptvault-install.log"
MARKER_KEY="receiptvault.installed"
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

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

normalize_ipv4_cidr() {
  local raw="${1// /}"
  local gw="${2:-}"
  raw="${raw#http://}"
  raw="${raw#https://}"
  raw="${raw%%:*}"
  if [[ -z "$raw" ]]; then
    return 1
  fi
  if [[ "$raw" != */* ]]; then
    if [[ -n "$gw" ]]; then
      raw="$(python3 - "$raw" "$gw" <<'PY'
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
gw = ipaddress.ip_address(sys.argv[2])
for prefix in (24, 16, 8):
    net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    if gw in net:
        print(f"{ip}/{prefix}")
        break
else:
    print(f"{ip}/16")
PY
)"
    else
      raw="${raw}/24"
    fi
  fi
  if ! python3 -c "import ipaddress,sys; ipaddress.ip_interface(sys.argv[1])" "$raw" 2>/dev/null; then
    return 1
  fi
  printf '%s\n' "$raw"
}

ipv4_from_cidr() { printf '%s\n' "${1%%/*}"; }

guess_gateway_from_cidr() {
  local ip="${1%%/*}"
  printf '%s\n' "${ip%.*}.1"
}

host_bridge_cidr() {
  ip -4 -o addr show dev "$1" 2>/dev/null | awk '{print $4; exit}'
}

suggest_static_cidr() {
  python3 - "$1" "${2:-13}" <<'PY'
import ipaddress, sys
net = ipaddress.ip_network(sys.argv[1], strict=False)
prefer = int(sys.argv[2])
hosts = list(net.hosts())
if not hosts:
    raise SystemExit(1)
chosen = None
for addr in hosts:
    if int(str(addr).rsplit(".", 1)[-1]) == prefer:
        chosen = addr
        break
if chosen is None:
    chosen = hosts[min(12, len(hosts) - 1)]
print(f"{chosen}/{net.prefixlen}")
PY
}

cidr_contains_address() {
  python3 - "$1" "$2" <<'PY'
import ipaddress, sys
net = ipaddress.ip_network(sys.argv[1], strict=False)
addr = ipaddress.ip_address(sys.argv[2].split("/")[0])
raise SystemExit(0 if addr in net else 1)
PY
}

public_url_for() {
  if [[ "$2" == "80" ]]; then
    printf 'http://%s\n' "$1"
  else
    printf 'http://%s:%s\n' "$1" "$2"
  fi
}

net0_line() {
  local bridge="$1" cidr="$2" gw="$3"
  local line="name=eth0,bridge=${bridge},firewall=0,ip=${cidr}"
  if [[ -n "$gw" ]]; then
    line="${line},gw=${gw}"
  fi
  printf '%s\n' "$line"
}

guest() {
  pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 LANGUAGE=C.UTF-8 DEBIAN_FRONTEND=noninteractive \
    bash -lc "$*" >>"$LOG" 2>&1
}

apply_guest_network() {
  local cidr="$1" gw="$2" dns="$3"
  pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    RV_CIDR="$cidr" RV_GATEWAY="$gw" RV_DNS="$dns" RV_IFACE=eth0 \
    bash -s >>"$LOG" 2>&1 <<'EOS'
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8
IFACE="${RV_IFACE:-eth0}"
CIDR="$RV_CIDR"
GATEWAY="${RV_GATEWAY:-}"
DNS="${RV_DNS:-1.1.1.1}"
[[ "$CIDR" == */* ]] || CIDR="${CIDR}/24"
ADDR="${CIDR%%/*}"
mkdir -p /etc/network /etc/sysctl.d
cat >/etc/network/interfaces <<EOF
auto lo
iface lo inet loopback

auto ${IFACE}
iface ${IFACE} inet static
    address ${CIDR}
    gateway ${GATEWAY}
    dns-nameservers ${DNS}
EOF
printf 'nameserver %s\n' "$DNS" >/etc/resolv.conf
sysctl -w net.ipv4.ip_unprivileged_port_start=0 >/dev/null 2>&1 || true
echo 'net.ipv4.ip_unprivileged_port_start=0' >/etc/sysctl.d/20-receiptvault-ports.conf
ip link set "$IFACE" up || true
if ! ip -4 addr show dev "$IFACE" | grep -q "inet ${ADDR}/"; then
  ip addr flush dev "$IFACE" 2>/dev/null || true
  ip addr add "$CIDR" dev "$IFACE"
fi
if [[ -n "$GATEWAY" ]]; then
  ip route replace default via "$GATEWAY" dev "$IFACE" 2>/dev/null || true
fi
ip -4 addr show dev "$IFACE" | grep -q "inet ${ADDR}/"
EOS
}

purge_guest_caddy() {
  if pct exec "$CTID" -- test -f /opt/receiptvault/deploy/purge-caddy.sh; then
    pct exec "$CTID" -- bash /opt/receiptvault/deploy/purge-caddy.sh >>"$LOG" 2>&1 || true
  else
    pct exec "$CTID" -- bash -lc 'systemctl disable --now caddy >/dev/null 2>&1 || true; systemctl mask caddy >/dev/null 2>&1 || true; apt-get purge -y caddy >/dev/null 2>&1 || true; rm -rf /etc/caddy /usr/share/caddy; pkill -9 caddy >/dev/null 2>&1 || true; fuser -k 80/tcp >/dev/null 2>&1 || true' >>"$LOG" 2>&1 || true
  fi
}

prepare_guest_locale() {
  guest 'apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends locales ca-certificates curl git
if [[ -f /etc/locale.gen ]]; then
  sed -i "s/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/" /etc/locale.gen
  sed -i "s/^# *en_AU.UTF-8 UTF-8/en_AU.UTF-8 UTF-8/" /etc/locale.gen
fi
locale-gen >/dev/null 2>&1 || true
update-locale LANG=C.UTF-8 LC_ALL=C.UTF-8 >/dev/null 2>&1 || true'
}

ask_static_network() {
  local raw cidr gw dns
  raw="$(ask "LXC IPv4 (CIDR optional)" "192.168.13.13")"
  gw="$(ask "Router / gateway (internet for inbox scan)" "192.168.1.1")"
  dns="$(ask "DNS" "1.1.1.1")"
  if ! cidr="$(normalize_ipv4_cidr "$raw" "$gw")"; then
    msg "That is not a valid IPv4 address."
    exit 1
  fi
  STATIC_CIDR="$cidr"
  STATIC_IP="$(ipv4_from_cidr "$cidr")"
  GW="$gw"
  DNS="$dns"
}

# If another LXC already has this IPv4 (a leftover Caddy CT is the usual case),
# take the address off it so the browser hits ReceiptVault, not the welcome page.
claim_static_ip_from_others() {
  local ip="$1" keep="${2:-}"
  local id name conf net0 new
  [[ -z "$ip" ]] && return 0
  if ip -4 addr show | grep -q "inet ${ip}/"; then
    echo "Removing ${ip} from the Proxmox host so the LXC can own it." | tee -a "$LOG"
    ip -4 -o addr show | awk -v i="$ip" '$4 ~ "^"i"/" {print $2, $4}' | while read -r iface cidr; do
      ip addr del "$cidr" dev "$iface" || true
    done
  fi
  systemctl disable --now caddy.service caddy.socket >/dev/null 2>&1 || true
  pkill -9 caddy >/dev/null 2>&1 || true
  while read -r id name; do
    [[ -z "$id" || "$id" == "$keep" ]] && continue
    conf="/etc/pve/lxc/${id}.conf"
    if [[ -f "$conf" ]] && grep -q "$ip" "$conf"; then
      echo "CT ${id} (${name}) already has ${ip}. Removing Caddy and that address." | tee -a "$LOG"
      if pct status "$id" 2>/dev/null | grep -q running; then
        pct exec "$id" -- env DEBIAN_FRONTEND=noninteractive bash -lc '
          systemctl disable --now caddy.service caddy.socket >/dev/null 2>&1 || true
          systemctl mask caddy.service >/dev/null 2>&1 || true
          pkill -9 caddy >/dev/null 2>&1 || true
          fuser -k 80/tcp >/dev/null 2>&1 || true
          apt-get purge -y caddy >/dev/null 2>&1 || true
          rm -rf /etc/caddy /usr/share/caddy
        ' >>"$LOG" 2>&1 || true
      fi
      net0="$(pct config "$id" 2>/dev/null | sed -n 's/^net0: //p' || true)"
      if [[ -n "$net0" && "$net0" == *"${ip}"* ]]; then
        new="$(printf '%s\n' "$net0" | sed -E "s/ip=${ip}\/[0-9]+/ip=dhcp/")"
        pct set "$id" --net0 "$new" >>"$LOG" 2>&1 || true
      fi
    fi
  done < <(pct list | awk 'NR>1 {print $1, $3}')
}

apply_ct_static_ip() {
  local bridge="$1"
  claim_static_ip_from_others "$STATIC_IP" "$CTID"
  pct set "$CTID" --net0 "$(net0_line "$bridge" "$STATIC_CIDR" "$GW")"
  if [[ -n "${DNS:-}" ]]; then
    pct set "$CTID" --nameserver "$DNS" || true
  fi
  apply_guest_network "$STATIC_CIDR" "$GW" "$DNS"
  if ! pct exec "$CTID" -- ip -4 addr show | grep -q "inet ${STATIC_IP}/"; then
    echo "The container does not have ${STATIC_IP} on eth0. See ${LOG}." | tee -a "$LOG"
    return 1
  fi
  return 0
}

update_public_url() {
  local url="$1"
  pct exec "$CTID" -- bash -lc "if [[ -f /etc/receiptvault/receiptvault.env ]]; then
  sed -i 's|^RECEIPTVAULT_PUBLIC_URL=.*|RECEIPTVAULT_PUBLIC_URL=${url}|' /etc/receiptvault/receiptvault.env
  grep -q '^RECEIPTVAULT_LAN_PORT=' /etc/receiptvault/receiptvault.env \
    && sed -i 's|^RECEIPTVAULT_LAN_PORT=.*|RECEIPTVAULT_LAN_PORT=${APPPORT}|' /etc/receiptvault/receiptvault.env \
    || echo RECEIPTVAULT_LAN_PORT=${APPPORT} >> /etc/receiptvault/receiptvault.env
fi"
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
ask() { $UI --title "$APP" --inputbox "$1" 12 78 "$2" 3>&1 1>&2 2>&3; }
yesno() { $UI --title "$APP" --yesno "$1" 14 78; }
menu() { $UI --title "$APP" --menu "$1" 22 78 12 "${@:2}" 3>&1 1>&2 2>&3; }
msg() { $UI --title "$APP" --msgbox "$1" 18 78; }
gauge() { $UI --title "$APP" --gauge "$1" 10 74 "$2"; }

$UI --title "$APP $VERSION" --msgbox "Installs an unprivileged Debian LXC and ${APP}.\n\nYou enter the LXC IPv4 and the router/gateway.\nAfter install, open http://<that-ip>/  (port 80).\n\nSource: ${REPO_URL}" 16 78

MODE="$(menu "What do you want to do?" \
  default "Default install (recommended)" \
  advanced "Advanced install (CPU, RAM, network, repo URL)" \
  network "Fix / change LAN IP on an existing CT" \
  repair "Repair / restart a recognised ReceiptVault CT" \
  update "Update application in a recognised CT" \
  backup "Create a backup inside a recognised CT" \
  restore "Restore (dry-run first) inside a recognised CT" \
  uninstall "Remove a recognised ReceiptVault CT")"

recognised() {
  local id="$1"
  pct exec "$id" -- test -f /opt/receiptvault/.installed
}

if [[ "$MODE" == "repair" || "$MODE" == "update" || "$MODE" == "backup" || "$MODE" == "restore" || "$MODE" == "uninstall" || "$MODE" == "network" ]]; then
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
      FIX_IP="$(ask "LAN IPv4 for this CT" "192.168.13.13")"
      FIX_GW="$(ask "Router / gateway" "192.168.1.1")"
      if pct exec "$CTID" -- test -f /opt/receiptvault/deploy/make-reachable.sh; then
        pct exec "$CTID" -- env RV_GATEWAY="$FIX_GW" bash /opt/receiptvault/deploy/make-reachable.sh "$FIX_IP" 80
      else
        pct exec "$CTID" -- env RV_IP="$FIX_IP" RV_PORT=80 RV_GATEWAY="$FIX_GW" bash /opt/receiptvault/deploy/repair-in-place.sh
      fi
      msg "Open this URL:\n\n  http://${FIX_IP}/"
      exit 0
      ;;
    network)
      BRIDGE="$(ask "Bridge" "vmbr0")"
      ask_static_network "$BRIDGE"
      yesno "Put ReceiptVault on ${STATIC_CIDR} and open as http://${STATIC_IP}/ ?" || exit 0
      apply_ct_static_ip "$BRIDGE" || true
      if pct exec "$CTID" -- test -f /opt/receiptvault/deploy/make-reachable.sh; then
        pct exec "$CTID" -- env RV_GATEWAY="$GW" bash /opt/receiptvault/deploy/make-reachable.sh "$STATIC_IP" 80
      fi
      PUBLIC="$(public_url_for "$STATIC_IP" 80)"
      msg "Open this URL:\n\n  ${PUBLIC}"
      log "Network updated CT $CTID ip=$STATIC_IP"
      echo -e "${GN}Open ${BL}${PUBLIC}${CL}"
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
STATIC_CIDR=""
STATIC_IP=""
GW=""
DNS="1.1.1.1"
APPPORT=80
if [[ "$MODE" == "advanced" ]]; then
  CORES="$(ask "vCPU" "4")"
  MEMORY="$(ask "RAM (MB)" "8192")"
  BRIDGE="$(ask "Bridge" "vmbr0")"
  NETMODE="$(menu "IPv4" static "Static IPv4 (recommended)" dhcp "DHCP")"
  if [[ "$NETMODE" == "static" ]]; then
    ask_static_network "$BRIDGE"
  fi
  APPPORT="$(ask "Browser port. 80 means open http://<ip>/ with no port." "80")"
  if yesno "Unprivileged container? (recommended: Yes)"; then UNPRIV=1; else UNPRIV=0; fi
  REPO_URL="$(ask "Git clone URL for ReceiptVault" "$REPO_URL")"
  REPO_REF="$(ask "Git ref (branch or tag)" "$REPO_REF")"
else
  CORES=4
  MEMORY=8192
  BRIDGE=vmbr0
  NETMODE=static
  UNPRIV=1
  ask_static_network "$BRIDGE"
  APPPORT=80
fi

EVIDENCE="$(menu "Evidence storage" \
  root "Store on the LXC root disk" \
  bindnew "Create a new host directory and bind-mount it" \
  bindexist "Bind-mount an existing host or NFS path")"
EVPATH="/var/lib/receiptvault/evidence"
if [[ "$EVIDENCE" != "root" ]]; then
  EVPATH="$(ask "Host evidence path" "$EVPATH")"
fi
CF="$(menu "Cloudflare Tunnel" \
  skip "LAN only (no public hostname)" \
  existing "I already have a tunnel — show origin settings" \
  managed "Install cloudflared in the LXC (token entered here, not logged)")"

SOURCE_NOTE="git ${REPO_URL}#${REPO_REF}"
[[ -n "$LOCAL_SOURCE" ]] && SOURCE_NOTE="local tree ${LOCAL_SOURCE} (fallback git ${REPO_URL})"

SUMMARY="CTID=${CTID}\nHostname=${HOSTNAME}\nStorage=${STORAGE}  Disk=${DISK}G  CPU=${CORES}  RAM=${MEMORY}MB\nBridge=${BRIDGE}  IPv4=${NETMODE} ${STATIC_CIDR}\nGateway=${GW}  DNS=${DNS}\nUnprivileged=${UNPRIV}\nEvidence=${EVIDENCE} ${EVPATH}\nPort=${APPPORT}  Cloudflare=${CF}\nSource=${SOURCE_NOTE}"
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

STATUS="/var/tmp/receiptvault-install.status"
rm -f "$STATUS"
(
  set -euo pipefail
  echo 8
  TEMPLATE="$(resolve_template || true)"
  if [[ -z "${TEMPLATE:-}" ]]; then
    echo "Debian 13 template not found. Select one with: pveam available --section system" | tee -a "$LOG"
    exit 1
  fi
  echo 18
  if [[ "$NETMODE" == "static" ]]; then
    NET="$(net0_line "$BRIDGE" "$STATIC_CIDR" "$GW")"
  else
    NET="name=eth0,bridge=${BRIDGE},firewall=0,ip=dhcp"
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
    --start 0 >>"$LOG" 2>&1
  if [[ -n "$DNS" ]]; then
    pct set "$CTID" --nameserver "$DNS" >>"$LOG" 2>&1 || true
  fi
  echo 32
  if [[ "$EVIDENCE" != "root" ]]; then
    mkdir -p "$EVPATH"
    echo "Bind-mounting ${EVPATH}. Unprivileged LXCs map container UIDs; if writes fail, chown the host path to the mapped UID of receiptvault (often 100000+)." | tee -a "$LOG"
    pct set "$CTID" --mp0 "${EVPATH},mp=/var/lib/receiptvault/evidence" >>"$LOG" 2>&1
  fi
  echo 40
  pct start "$CTID" >>"$LOG" 2>&1
  for _ in $(seq 1 40); do
    if pct exec "$CTID" -- true >/dev/null 2>&1; then break; fi
    sleep 1
  done
  echo 48
  prepare_guest_locale
  if [[ "$NETMODE" == "static" ]]; then
    apply_ct_static_ip "$BRIDGE"
  fi
  echo 58
  guest 'mkdir -p /opt/receiptvault /etc/receiptvault'
  if [[ -n "$LOCAL_SOURCE" ]]; then
    tar -C "$LOCAL_SOURCE" --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='backend/.venv' --exclude='var' --exclude='frontend/node_modules' -cf - . \
      | pct exec "$CTID" -- tar -C /opt/receiptvault -xf -
  else
    guest "git clone --depth 1 --branch '${REPO_REF}' '${REPO_URL}' /opt/receiptvault"
  fi
  echo 70
  if [[ "$NETMODE" == "static" ]]; then
    ACCESS_IP="$STATIC_IP"
  else
    ACCESS_IP="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
  fi
  PUBLIC="$(public_url_for "$ACCESS_IP" "$APPPORT")"
  pct exec "$CTID" -- tee /etc/receiptvault/receiptvault.env >/dev/null <<ENVEOF
RECEIPTVAULT_ENV=production
RECEIPTVAULT_PUBLIC_URL=${PUBLIC}
RECEIPTVAULT_LAN_PORT=${APPPORT}
RECEIPTVAULT_API_HOST=0.0.0.0
RECEIPTVAULT_API_PORT=${APPPORT}
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
RECEIPTVAULT_STATIC_CIDR=${STATIC_CIDR}
RECEIPTVAULT_GATEWAY=${GW}
RECEIPTVAULT_DNS=${DNS}
ENVEOF
  pct exec "$CTID" -- chmod 600 /etc/receiptvault/receiptvault.env
  echo 78
  guest 'bash /opt/receiptvault/deploy/lxc-bootstrap.sh'
  echo 92
  if [[ "$NETMODE" == "static" ]]; then
    apply_ct_static_ip "$BRIDGE" || true
    ACCESS_IP="$STATIC_IP"
  else
    ACCESS_IP="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
  fi
  PUBLIC="$(public_url_for "$ACCESS_IP" "$APPPORT")"
  update_public_url "$PUBLIC"
  purge_guest_caddy || true
  pct exec "$CTID" -- systemctl restart receiptvault >>"$LOG" 2>&1 || true
  pct exec "$CTID" -- bash -lc "echo ${MARKER_KEY}=${VERSION} > /opt/receiptvault/.installed"
  if [[ -n "${ACCESS_IP:-}" ]]; then
    claim_static_ip_from_others "$ACCESS_IP" "$CTID"
    page="$(curl -sS --connect-timeout 5 "http://${ACCESS_IP}/" || true)"
    if echo "$page" | grep -qi 'Your web server is working\|Congratulations'; then
      echo "http://${ACCESS_IP}/ is still Caddy. Taking the IP again and rechecking." | tee -a "$LOG"
      claim_static_ip_from_others "$ACCESS_IP" "$CTID"
      pct exec "$CTID" -- bash /opt/receiptvault/deploy/purge-caddy.sh >>"$LOG" 2>&1 || true
      pct exec "$CTID" -- systemctl restart receiptvault >>"$LOG" 2>&1 || true
      sleep 2
      page="$(curl -sS --connect-timeout 5 "http://${ACCESS_IP}/" || true)"
    fi
    if echo "$page" | grep -qi 'Your web server is working\|Congratulations'; then
      echo "REFUSING to mark the install OK: http://${ACCESS_IP}/ is still the Caddy welcome page." | tee -a "$LOG"
      exit 1
    fi
  fi
  echo 100
  echo OK >"$STATUS"
) | gauge "Installing ${APP}" 0

if [[ ! -f "$STATUS" ]]; then
  msg "Install did not finish. Locale warnings during apt are normal; a real failure is in:\n\n  ${LOG}\n  pct exec ${CTID} -- tail -n 80 /var/log/receiptvault-bootstrap.log\n\nYou can re-run this helper and choose Repair, Fix / change LAN IP, or Uninstall."
  exit 1
fi

if [[ "$NETMODE" == "static" ]]; then
  ACCESS_IP="$STATIC_IP"
else
  ACCESS_IP="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
fi
PUBLIC="$(public_url_for "$ACCESS_IP" "$APPPORT")"
ORIGIN="$PUBLIC"

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

FINAL="ReceiptVault CT ${CTID} is ready.\n\nOpen:\n  ${PUBLIC}\n\nCreate the owner account there. Then add Entra app credentials, connect three inboxes, pick audit years, and start the first scan.\n\nExisting Cloudflare Tunnel origin:\n  ${ORIGIN}\n\nInstall log (secrets redacted): ${LOG}\n\nTo change the IP later, re-run this helper and choose Fix / change LAN IP."
msg "$FINAL"
log "Completed CT $CTID ip=$ACCESS_IP port=$APPPORT url=$PUBLIC"
echo -e "${GN}Done.${CL} Open ${BL}${PUBLIC}${CL}"
