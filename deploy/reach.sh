#!/usr/bin/env bash
# Force ReceiptVault onto 192.168.13.14/20 and start the app.
# Run as root on the Proxmox host:
#   cd /root/ReceiptVault
#   git pull
#   bash deploy/reach.sh
echo "ReceiptVault — put the CT on 192.168.13.14/20"
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-network.sh
source "${SCRIPT_DIR}/lib-network.sh"

if [[ ${EUID} -ne 0 ]] || ! command -v pct >/dev/null; then
  echo "Run as root on the Proxmox host."
  exit 1
fi

LXC_IP="${RECEIPTVAULT_LXC_IP:-192.168.13.14}"
PREFIX="${RECEIPTVAULT_PREFIX:-20}"
BRIDGE="${RECEIPTVAULT_BRIDGE:-vmbr0}"
DNS="${RECEIPTVAULT_DNS:-1.1.1.1}"
LXC_CIDR="${LXC_IP}/${PREFIX}"

find_ct() {
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
  echo "No ReceiptVault container. pct list:"
  pct list
  echo "Run bash ${SCRIPT_DIR}/install-receiptvault.sh and choose Default install."
  exit 1
fi

GW="$(host_ipv4_on_bridge "$BRIDGE" 2>/dev/null || true)"
if [[ -z "$GW" ]]; then
  echo "No IPv4 on ${BRIDGE}. Cannot set the gateway."
  ip -4 addr || true
  exit 1
fi

if ! pct status "$CTID" | grep -q running; then
  echo "Starting CT ${CTID}"
  pct start "$CTID"
  sleep 4
fi

echo "CT ${CTID}  ${LXC_CIDR}  gateway ${GW}"
pct set "$CTID" --net0 "name=eth0,bridge=${BRIDGE},firewall=0,ip=${LXC_CIDR},gw=${GW}"
pct set "$CTID" --nameserver "$DNS" || true

pct exec "$CTID" -- mkdir -p /opt/receiptvault/deploy
pct push "$CTID" "${SCRIPT_DIR}/guest-network.sh" /opt/receiptvault/deploy/guest-network.sh
pct exec "$CTID" -- chmod 0755 /opt/receiptvault/deploy/guest-network.sh

pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  RV_CIDR="$LXC_CIDR" RV_GATEWAY="$GW" RV_DNS="$DNS" RV_IFACE=eth0 \
  bash /opt/receiptvault/deploy/guest-network.sh

pct exec "$CTID" -- bash /opt/receiptvault/deploy/purge-caddy.sh 2>/dev/null || true
pct exec "$CTID" -- bash -lc "ENV=/etc/receiptvault/receiptvault.env
if [[ -f \$ENV ]]; then
  grep -q '^RECEIPTVAULT_PUBLIC_URL=' \$ENV \
    && sed -i 's|^RECEIPTVAULT_PUBLIC_URL=.*|RECEIPTVAULT_PUBLIC_URL=http://${LXC_IP}|' \$ENV \
    || echo RECEIPTVAULT_PUBLIC_URL=http://${LXC_IP} >>\$ENV
  grep -q '^RECEIPTVAULT_LAN_PORT=' \$ENV \
    && sed -i 's|^RECEIPTVAULT_LAN_PORT=.*|RECEIPTVAULT_LAN_PORT=80|' \$ENV \
    || echo RECEIPTVAULT_LAN_PORT=80 >>\$ENV
  grep -q '^RECEIPTVAULT_API_HOST=' \$ENV \
    && sed -i 's|^RECEIPTVAULT_API_HOST=.*|RECEIPTVAULT_API_HOST=0.0.0.0|' \$ENV \
    || echo RECEIPTVAULT_API_HOST=0.0.0.0 >>\$ENV
  grep -q '^RECEIPTVAULT_API_PORT=' \$ENV \
    && sed -i 's|^RECEIPTVAULT_API_PORT=.*|RECEIPTVAULT_API_PORT=80|' \$ENV \
    || echo RECEIPTVAULT_API_PORT=80 >>\$ENV
fi
sysctl -w net.ipv4.ip_unprivileged_port_start=0 >/dev/null 2>&1 || true
systemctl restart postgresql redis-server receiptvault 2>/dev/null || systemctl restart receiptvault
"

HEALTH=""
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  HEALTH="$(pct exec "$CTID" -- curl -sS --connect-timeout 2 http://127.0.0.1/health/live 2>/dev/null || true)"
  [[ "$HEALTH" == *ok* ]] && break
  sleep 1
done
echo "Inside CT: ${HEALTH:-NONE}"
echo "CT addresses:"
pct exec "$CTID" -- ip -4 addr show eth0 || true
if [[ "$HEALTH" != *ok* ]]; then
  echo "App is not listening on port 80 inside the CT."
  pct exec "$CTID" -- journalctl -u receiptvault -n 40 --no-pager || true
  exit 1
fi

echo
echo "OPEN THIS:"
echo "  http://${LXC_IP}/"
echo "http  —  not https"
