#!/usr/bin/env bash
# Run as root on the Proxmox HOST (the machine with pct), not inside the LXC.
#
#   wget -O /root/fix-receiptvault.sh \
#     https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/fix-from-host.sh
#   bash /root/fix-receiptvault.sh
#
# Optional: bash /root/fix-receiptvault.sh <CTID> <PORT> <LXC_IP>
# Default LXC address is 192.168.13.13 (host stays on 192.168.14.1).
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this as root in the Proxmox shell (the same place you run pct)."
  exit 1
fi
if ! command -v pct >/dev/null; then
  echo "pct not found. This script is for the Proxmox host, not the container."
  exit 1
fi

PORT="${2:-8082}"
LXC_IP="${3:-${RECEIPTVAULT_LXC_IP:-192.168.13.13}}"
MGMT_BRIDGE="${RECEIPTVAULT_MGMT_BRIDGE:-vmbr0}"

pick_lxc_bridge() {
  local net="${1%.*}"
  local br
  if [[ -n "${RECEIPTVAULT_BRIDGE:-}" ]]; then
    printf '%s\n' "$RECEIPTVAULT_BRIDGE"
    return 0
  fi
  for br in $(ip -o link show | awk -F': ' '/vmbr[0-9]/ {gsub(/@.*/,"",$2); print $2}'); do
    if ip -4 addr show dev "$br" 2>/dev/null | grep -q "inet ${net}\\."; then
      printf '%s\n' "$br"
      return 0
    fi
  done
  if ip link show vmbr1 >/dev/null 2>&1; then
    printf '%s\n' vmbr1
    return 0
  fi
  printf '%s\n' "$MGMT_BRIDGE"
}

find_ct() {
  local id
  if [[ -n "${1:-}" ]]; then
    echo "$1"
    return 0
  fi
  while read -r id name; do
    [[ "$name" == *receiptvault* ]] && echo "$id" && return 0
  done < <(pct list | awk 'NR>1 {print $1, $3}')
  while read -r id; do
    if pct exec "$id" -- test -d /opt/receiptvault 2>/dev/null; then
      echo "$id"
      return 0
    fi
  done < <(pct list | awk 'NR>1 {print $1}')
  return 1
}

CTID="$(find_ct "${1:-}" || true)"
if [[ -z "$CTID" ]]; then
  echo "Could not find a ReceiptVault container. Running containers:"
  pct list
  echo "Re-run as: bash $0 <CTID> ${PORT} ${LXC_IP}"
  exit 1
fi

echo "==== Using CT ${CTID}  LXC ${LXC_IP}  port ${PORT} ===="
pct list | awk -v id="$CTID" 'NR==1 || $1==id'

if ! pct status "$CTID" | grep -q running; then
  echo "Starting container ${CTID}"
  pct start "$CTID"
  sleep 3
fi

HOST_CIDR="$(ip -4 -o addr show dev "$MGMT_BRIDGE" 2>/dev/null | awk '{print $4; exit}')"
if [[ -z "$HOST_CIDR" ]]; then
  echo "Management bridge ${MGMT_BRIDGE} has no IPv4 address. Interfaces:"
  ip -4 -o addr
  exit 1
fi
HOST_IP="${HOST_CIDR%%/*}"
BRIDGE="$(pick_lxc_bridge "$LXC_IP")"
LXC_CIDR="${LXC_IP}/24"
EXISTING_GW="$(ip -4 -o addr show dev "$BRIDGE" 2>/dev/null | awk '{print $4}' | grep "^${LXC_IP%.*}\\." | head -1 || true)"
if [[ -n "$EXISTING_GW" ]]; then
  LXC_GW="${EXISTING_GW%%/*}"
else
  LXC_GW="${LXC_IP%.*}.1"
fi

echo
echo "Dedicated-server layout:"
echo "  Proxmox management: ${HOST_IP} on ${MGMT_BRIDGE}"
echo "  ReceiptVault LXC:   ${LXC_IP}/24 on ${BRIDGE} (gateway ${LXC_GW})"
echo "  Bridges on this host:"
ip -4 -o addr show | awk '/vmbr/ {print "   ", $2, $4}'
echo
echo "Forwarding ${HOST_IP}:${PORT} -> ${LXC_IP}:${PORT}"
echo

if ! ip -4 addr show dev "$BRIDGE" | grep -q "inet ${LXC_GW}/"; then
  ip addr add "${LXC_GW}/24" dev "$BRIDGE"
fi
sysctl -w net.ipv4.ip_forward=1 >/dev/null
mkdir -p /etc/sysctl.d
echo 'net.ipv4.ip_forward=1' >/etc/sysctl.d/99-receiptvault-forward.conf

add_fwd() {
  iptables -t nat -C PREROUTING -p tcp --dport "$PORT" -j DNAT --to-destination "${LXC_IP}:${PORT}" 2>/dev/null \
    || iptables -t nat -A PREROUTING -p tcp --dport "$PORT" -j DNAT --to-destination "${LXC_IP}:${PORT}"
  iptables -t nat -C OUTPUT -p tcp --dport "$PORT" -d "$HOST_IP" -j DNAT --to-destination "${LXC_IP}:${PORT}" 2>/dev/null \
    || iptables -t nat -A OUTPUT -p tcp --dport "$PORT" -d "$HOST_IP" -j DNAT --to-destination "${LXC_IP}:${PORT}"
  iptables -t nat -C POSTROUTING -d "$LXC_IP" -p tcp --dport "$PORT" -j MASQUERADE 2>/dev/null \
    || iptables -t nat -A POSTROUTING -d "$LXC_IP" -p tcp --dport "$PORT" -j MASQUERADE
  iptables -C FORWARD -p tcp -d "$LXC_IP" --dport "$PORT" -j ACCEPT 2>/dev/null \
    || iptables -A FORWARD -p tcp -d "$LXC_IP" --dport "$PORT" -j ACCEPT
}
add_fwd

cat >/usr/local/sbin/receiptvault-forward.sh <<FWD
#!/bin/bash
ip addr show dev ${BRIDGE} | grep -q 'inet ${LXC_GW}/' || ip addr add ${LXC_GW}/24 dev ${BRIDGE}
sysctl -w net.ipv4.ip_forward=1 >/dev/null
iptables -t nat -C PREROUTING -p tcp --dport ${PORT} -j DNAT --to-destination ${LXC_IP}:${PORT} 2>/dev/null \\
  || iptables -t nat -A PREROUTING -p tcp --dport ${PORT} -j DNAT --to-destination ${LXC_IP}:${PORT}
iptables -t nat -C OUTPUT -p tcp --dport ${PORT} -d ${HOST_IP} -j DNAT --to-destination ${LXC_IP}:${PORT} 2>/dev/null \\
  || iptables -t nat -A OUTPUT -p tcp --dport ${PORT} -d ${HOST_IP} -j DNAT --to-destination ${LXC_IP}:${PORT}
iptables -t nat -C POSTROUTING -d ${LXC_IP} -p tcp --dport ${PORT} -j MASQUERADE 2>/dev/null \\
  || iptables -t nat -A POSTROUTING -d ${LXC_IP} -p tcp --dport ${PORT} -j MASQUERADE
iptables -C FORWARD -p tcp -d ${LXC_IP} --dport ${PORT} -j ACCEPT 2>/dev/null \\
  || iptables -A FORWARD -p tcp -d ${LXC_IP} --dport ${PORT} -j ACCEPT
FWD
chmod 0755 /usr/local/sbin/receiptvault-forward.sh
cat >/etc/systemd/system/receiptvault-forward.service <<'UNIT'
[Unit]
Description=ReceiptVault host forward (.14 laptop -> .13 LXC)
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/receiptvault-forward.sh
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now receiptvault-forward.service >/dev/null

pct set "$CTID" --firewall 0 >/dev/null || true
pct set "$CTID" --net0 "name=eth0,bridge=${BRIDGE},firewall=0,ip=${LXC_CIDR},gw=${LXC_GW}"
pct set "$CTID" --nameserver 1.1.1.1 >/dev/null || true

echo "Waiting for the container shell..."
for _ in $(seq 1 30); do
  if pct exec "$CTID" -- true >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "Applying ${LXC_CIDR} inside the container (gateway ${LXC_GW})"
pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  RV_CIDR="$LXC_CIDR" RV_GATEWAY="$LXC_GW" RV_DNS=1.1.1.1 bash -s <<'EOS'
set -euo pipefail
IFACE=eth0
CIDR="$RV_CIDR"
GW="$RV_GATEWAY"
ADDR="${CIDR%%/*}"
mkdir -p /etc/network /etc/sysctl.d
cat >/etc/network/interfaces <<EOF
auto lo
iface lo inet loopback

auto ${IFACE}
iface ${IFACE} inet static
    address ${CIDR}
    gateway ${GW}
    dns-nameservers 1.1.1.1
EOF
printf 'nameserver 1.1.1.1\n' >/etc/resolv.conf
ip link set "$IFACE" up || true
if ! ip -4 addr show dev "$IFACE" | grep -q "inet ${ADDR}/"; then
  ip addr flush dev "$IFACE" 2>/dev/null || true
  ip addr add "$CIDR" dev "$IFACE"
fi
ip route replace default via "$GW" dev "$IFACE" 2>/dev/null || true
ip -4 addr show dev "$IFACE"
EOS

if ! pct exec "$CTID" -- test -d /opt/receiptvault/backend; then
  echo "This container has no /opt/receiptvault. The original install did not finish."
  echo "Re-run the installer after this network is working, or pick another CTID."
  exit 1
fi

echo "Stopping Caddy and starting ReceiptVault on 0.0.0.0:${PORT}"
pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  RV_IP="$LXC_IP" RV_PORT="$PORT" bash -s <<'EOS'
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:$PATH"
APP=/opt/receiptvault
ENV=/etc/receiptvault/receiptvault.env
IP="$RV_IP"
PORT="$RV_PORT"
PUBLIC="http://${IP}:${PORT}"

systemctl disable --now caddy >/dev/null 2>&1 || true
systemctl mask caddy >/dev/null 2>&1 || true
# Make sure nothing else owns :80 with the Caddy welcome page
if ss -lnt | grep -q ':80 '; then
  fuser -k 80/tcp >/dev/null 2>&1 || true
fi

id receiptvault >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin receiptvault
chown -R receiptvault:receiptvault "$APP" /var/lib/receiptvault 2>/dev/null || true

if [[ ! -x "$APP/backend/.venv/bin/uvicorn" ]]; then
  echo "Python venv missing — running uv sync (this can take a few minutes)"
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
  cd "$APP/backend"
  runuser -u receiptvault -- env PATH="$PATH" uv sync --frozen --no-dev || \
    runuser -u receiptvault -- env PATH="$PATH" uv sync --no-dev
fi
if [[ ! -f "$APP/frontend/dist/index.html" ]]; then
  echo "UI build missing — running npm run build (this can take a few minutes)"
  cd "$APP/frontend"
  if [[ -f package-lock.json ]]; then
    runuser -u receiptvault -- env PATH="$PATH" npm ci
  else
    runuser -u receiptvault -- env PATH="$PATH" npm install
  fi
  runuser -u receiptvault -- env PATH="$PATH" npm run build
fi
chmod -R a+rX "$APP/frontend/dist" || true
ln -sfn "$APP/backend/.venv" "$APP/.venv"

install -d -m 0700 /etc/receiptvault
if [[ -f "$ENV" ]]; then
  grep -q '^RECEIPTVAULT_PUBLIC_URL=' "$ENV" && sed -i "s|^RECEIPTVAULT_PUBLIC_URL=.*|RECEIPTVAULT_PUBLIC_URL=${PUBLIC}|" "$ENV" || echo "RECEIPTVAULT_PUBLIC_URL=${PUBLIC}" >>"$ENV"
  grep -q '^RECEIPTVAULT_LAN_PORT=' "$ENV" && sed -i "s|^RECEIPTVAULT_LAN_PORT=.*|RECEIPTVAULT_LAN_PORT=${PORT}|" "$ENV" || echo "RECEIPTVAULT_LAN_PORT=${PORT}" >>"$ENV"
  grep -q '^RECEIPTVAULT_API_HOST=' "$ENV" && sed -i "s|^RECEIPTVAULT_API_HOST=.*|RECEIPTVAULT_API_HOST=0.0.0.0|" "$ENV" || echo "RECEIPTVAULT_API_HOST=0.0.0.0" >>"$ENV"
  grep -q '^RECEIPTVAULT_API_PORT=' "$ENV" && sed -i "s|^RECEIPTVAULT_API_PORT=.*|RECEIPTVAULT_API_PORT=${PORT}|" "$ENV" || echo "RECEIPTVAULT_API_PORT=${PORT}" >>"$ENV"
else
  echo "No $ENV — cannot start (installer never wrote secrets). Re-run the helper install."
  exit 1
fi

mkdir -p "$APP/deploy"
cat >"$APP/deploy/run-api.sh" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/receiptvault/backend
PORT="${RECEIPTVAULT_LAN_PORT:-${RECEIPTVAULT_API_PORT:-8082}}"
HOST="${RECEIPTVAULT_API_HOST:-0.0.0.0}"
exec /opt/receiptvault/backend/.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
RUN
chmod 0755 "$APP/deploy/run-api.sh"

cat >/etc/systemd/system/receiptvault.service <<'UNIT'
[Unit]
Description=ReceiptVault API
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
Type=simple
User=receiptvault
Group=receiptvault
EnvironmentFile=/etc/receiptvault/receiptvault.env
WorkingDirectory=/opt/receiptvault/backend
ExecStart=/opt/receiptvault/deploy/run-api.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now postgresql redis-server >/dev/null 2>&1 || true
systemctl enable receiptvault >/dev/null
systemctl restart postgresql redis-server || true
systemctl restart receiptvault

ok=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${PORT}/health/live" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "---- receiptvault service logs ----"
  journalctl -u receiptvault -n 60 --no-pager || true
  echo "---- listening ports ----"
  ss -lntp || true
  exit 1
fi
echo "Guest health OK on 127.0.0.1:${PORT}"
EOS

echo
echo "==== Probe from the Proxmox host ===="
CODE_LXC="$(curl -sS -o /tmp/rv-fix-body -w '%{http_code}' --connect-timeout 5 "http://${LXC_IP}:${PORT}/" || echo 000)"
echo "http://${LXC_IP}:${PORT}/     -> HTTP ${CODE_LXC}"
CODE_FWD="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 "http://${HOST_IP}:${PORT}/" || echo 000)"
echo "http://${HOST_IP}:${PORT}/     -> HTTP ${CODE_FWD}  (forward from host)"
head -c 200 /tmp/rv-fix-body 2>/dev/null; echo

if [[ "$CODE_LXC" != "200" && "$CODE_FWD" != "200" ]]; then
  echo
  echo "Host could not load the app."
  echo "Container addresses:"
  pct exec "$CTID" -- ip -4 addr
  echo "Container logs:"
  pct exec "$CTID" -- journalctl -u receiptvault -n 40 --no-pager || true
  exit 1
fi

echo
echo "=============================================="
echo "  LXC address is ${LXC_IP} (unchanged)."
echo
echo "  From the laptop that already opens Proxmox:"
echo "    http://${HOST_IP}:${PORT}/"
echo
echo "  From anything on the 192.168.13.x network:"
echo "    http://${LXC_IP}:${PORT}/"
echo "=============================================="
