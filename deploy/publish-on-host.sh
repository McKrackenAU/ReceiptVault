#!/usr/bin/env bash
# Put ReceiptVault on this Proxmox HOST so the desktop can open it.
# The desktop already reaches this machine at :8006. Port 80 and 8484
# on the same IPv4 are the browser URLs. The LXC can stay on 192.168.13.14.
#
#   bash /root/ReceiptVault/deploy/publish-on-host.sh
echo "ReceiptVault 1.5.3 — publish on this Proxmox host"
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8

if [[ ${EUID} -ne 0 ]] || ! command -v pct >/dev/null; then
  echo "Run as root on the Proxmox host."
  exit 1
fi

CTID="${1:-}"

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

CTID="$(find_ct "$CTID" || true)"
if [[ -z "$CTID" ]]; then
  echo "No ReceiptVault container. pct list:"
  pct list
  echo "Run: bash /root/ReceiptVault/deploy/install-receiptvault.sh"
  echo "Choose Default install."
  exit 1
fi

if ! pct status "$CTID" | grep -q running; then
  echo "Starting CT ${CTID}"
  pct start "$CTID"
  sleep 5
fi

echo "CT ${CTID}"
pct exec "$CTID" -- systemctl restart postgresql redis-server receiptvault 2>/dev/null || \
  pct exec "$CTID" -- systemctl restart receiptvault || true

GUEST_HEALTH=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
  GUEST_HEALTH="$(pct exec "$CTID" -- curl -sS --connect-timeout 2 http://127.0.0.1/health/live 2>/dev/null || true)"
  [[ "$GUEST_HEALTH" == *ok* ]] && break
  sleep 1
done
echo "Inside CT health: ${GUEST_HEALTH:-NONE}"
if [[ "$GUEST_HEALTH" != *ok* ]]; then
  echo "App is not up inside the CT. Last log:"
  pct exec "$CTID" -- journalctl -u receiptvault -n 40 --no-pager || true
  exit 1
fi

CT_IP="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "$CT_IP" ]]; then
  CT_IP="$(pct config "$CTID" | sed -n 's/.*ip=\([0-9.]*\).*/\1/p' | head -n 1)"
fi
if [[ -z "$CT_IP" ]]; then
  echo "CT has no IPv4."
  pct config "$CTID" || true
  exit 1
fi
echo "CT address: ${CT_IP}"

BRIDGE="$(pct config "$CTID" | sed -n 's/.*bridge=\([^,]*\).*/\1/p' | head -n 1)"
BRIDGE="${BRIDGE:-vmbr0}"
ip route replace "${CT_IP}/32" dev "$BRIDGE" 2>/dev/null || true

HOST_IP="$(ip -4 -o addr show dev "$BRIDGE" 2>/dev/null | awk '{print $4; exit}' | cut -d/ -f1)"
if [[ -z "$HOST_IP" ]]; then
  HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [[ -z "$HOST_IP" ]]; then
  echo "This host has no IPv4 on ${BRIDGE}."
  exit 1
fi

# Desktop browsers that already open the Proxmox UI can use this host IPv4.
# Listen on 80 (same as a normal website) and 8484 if 80 is taken.
PORTS=""
for p in 80 8484; do
  if python3 - "$p" <<'PY'
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("0.0.0.0", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
  then
    PORTS="${PORTS} ${p}"
  fi
done
PORTS="${PORTS# }"
if [[ -z "$PORTS" ]]; then
  echo "Host ports 80 and 8484 are both in use."
  ss -lnt || netstat -lnt || true
  exit 1
fi
echo "Host will listen on:${PORTS}"

PUBLIC_URL="http://${HOST_IP}"
if [[ " $PORTS " != *" 80 "* ]]; then
  PUBLIC_URL="http://${HOST_IP}:8484"
fi
if pct exec "$CTID" -- test -f /etc/receiptvault/receiptvault.env; then
  pct exec "$CTID" -- bash -lc "ENV=/etc/receiptvault/receiptvault.env
grep -q '^RECEIPTVAULT_PUBLIC_URL=' \"\$ENV\" \
  && sed -i 's|^RECEIPTVAULT_PUBLIC_URL=.*|RECEIPTVAULT_PUBLIC_URL=${PUBLIC_URL}|' \"\$ENV\" \
  || echo RECEIPTVAULT_PUBLIC_URL=${PUBLIC_URL} >>\"\$ENV\""
  pct exec "$CTID" -- systemctl restart receiptvault || true
  for _ in 1 2 3 4 5 6 7 8; do
    pct exec "$CTID" -- curl -sS --connect-timeout 2 http://127.0.0.1/health/live 2>/dev/null | grep -q ok && break
    sleep 1
  done
fi

mkdir -p /usr/local/sbin /etc
printf '%s\n' "${CT_IP}" >/etc/receiptvault-proxy.target
printf '%s\n' "${PORTS}" >/etc/receiptvault-proxy.ports
cat >/usr/local/sbin/receiptvault-proxy.py <<'PY'
#!/usr/bin/python3
import pathlib
import select
import socket
import threading

dest_ip = pathlib.Path("/etc/receiptvault-proxy.target").read_text().strip()
dest_port = 80
ports = [int(p) for p in pathlib.Path("/etc/receiptvault-proxy.ports").read_text().split() if p.strip()]
if not ports:
    ports = [80, 8484]


def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        try:
            a.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def handle(client):
    try:
        upstream = socket.create_connection((dest_ip, dest_port), timeout=10)
    except OSError:
        client.close()
        return
    threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
    pipe(upstream, client)
    for s in (client, upstream):
        try:
            s.close()
        except OSError:
            pass


listeners = []
for port in ports:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(64)
    listeners.append(sock)
    print(f"proxy 0.0.0.0:{port} -> {dest_ip}:{dest_port}", flush=True)

while True:
    ready, _, _ = select.select(listeners, [], [])
    for sock in ready:
        client, _ = sock.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()
PY
chmod 0755 /usr/local/sbin/receiptvault-proxy.py

cat >/etc/systemd/system/receiptvault-proxy.service <<'UNIT'
[Unit]
Description=ReceiptVault access on the Proxmox host IP
After=network.target
[Service]
ExecStart=/usr/bin/python3 /usr/local/sbin/receiptvault-proxy.py
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now receiptvault-proxy
systemctl restart receiptvault-proxy

open_port() {
  local port="$1"
  if command -v iptables >/dev/null; then
    iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
      || iptables -I INPUT -p tcp --dport "$port" -j ACCEPT || true
  fi
  if command -v nft >/dev/null; then
    nft list ruleset 2>/dev/null | grep -q "tcp dport ${port} accept" \
      || nft insert rule inet filter input tcp dport "$port" accept 2>/dev/null || true
  fi
}

NODE="$(hostname -s 2>/dev/null || true)"
FW=""
if [[ -n "$NODE" && -d /etc/pve/nodes/${NODE} ]]; then
  FW="/etc/pve/nodes/${NODE}/host.fw"
fi
for p in $PORTS; do
  open_port "$p"
  if [[ -n "$FW" ]]; then
    touch "$FW"
    grep -q "dport ${p}.*ReceiptVault" "$FW" 2>/dev/null \
      || printf '\nIN ACCEPT -p tcp -dport %s # ReceiptVault\n' "$p" >>"$FW"
  fi
done
if command -v pve-firewall >/dev/null; then
  pve-firewall compile >/dev/null 2>&1 || true
fi
sleep 1

OK_URL=""
for p in $PORTS; do
  if [[ "$p" == "80" ]]; then
    try="http://${HOST_IP}/"
    localtry="http://127.0.0.1/"
  else
    try="http://${HOST_IP}:${p}/"
    localtry="http://127.0.0.1:${p}/"
  fi
  code="$(curl -sS -o /tmp/rv-host-body -w '%{http_code}' --connect-timeout 5 "$localtry" || echo 000)"
  echo "Host ${localtry} -> HTTP ${code}"
  if [[ "$code" == "200" ]]; then
    OK_URL="$try"
    break
  fi
done

if [[ -z "$OK_URL" ]]; then
  echo "Host proxy did not return the app."
  journalctl -u receiptvault-proxy -n 30 --no-pager || true
  curl -sS -o /tmp/rv-ct-body -w "direct http://${CT_IP}/ -> %{http_code}\n" --connect-timeout 5 "http://${CT_IP}/" || true
  exit 1
fi

if [[ -f /root/ReceiptVault/deploy/install-host-command.sh ]]; then
  bash /root/ReceiptVault/deploy/install-host-command.sh || true
fi

echo
echo "OPEN THIS:"
echo "  http://${CT_IP}/"
echo "http, not https. LAN is /20."
echo "http://${CT_IP}/" >/etc/receiptvault-open.url
echo "Later: receiptvault-update"
