#!/usr/bin/env bash
# Publish ReceiptVault on the Proxmox HOST IP, same machine as :8006.
# On the host:
#   bash /root/ReceiptVault/deploy/publish-on-host.sh
echo "ReceiptVault 1.5.2 — publish on the Proxmox host IP"
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8

if [[ ${EUID} -ne 0 ]] || ! command -v pct >/dev/null; then
  echo "Run as root on the Proxmox host."
  exit 1
fi

CTID="${1:-}"
HOST_PORT="${RECEIPTVAULT_HOST_PORT:-8484}"

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
  echo "No ReceiptVault CT. pct list:"
  pct list
  echo "Usage: bash $0 <CTID>"
  exit 1
fi

if ! pct status "$CTID" | grep -q running; then
  echo "Starting CT ${CTID}"
  pct start "$CTID"
  sleep 4
fi

echo "CT ${CTID}"
pct exec "$CTID" -- systemctl restart postgresql redis-server receiptvault 2>/dev/null || \
  pct exec "$CTID" -- systemctl restart receiptvault || true
sleep 2

GUEST_HEALTH="$(pct exec "$CTID" -- curl -sS --connect-timeout 3 http://127.0.0.1/health/live 2>/dev/null || true)"
echo "Inside CT health: ${GUEST_HEALTH:-NONE}"
if [[ "$GUEST_HEALTH" != *ok* ]]; then
  echo "App is not up inside the CT. Last log:"
  pct exec "$CTID" -- journalctl -u receiptvault -n 30 --no-pager || true
  exit 1
fi

CT_IP="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "$CT_IP" ]]; then
  CT_IP="$(pct config "$CTID" | sed -n 's/.*ip=\([0-9.]*\).*/\1/p' | head -n 1)"
fi
echo "CT address: ${CT_IP:-unknown}"

BRIDGE="$(pct config "$CTID" | sed -n 's/.*bridge=\([^,]*\).*/\1/p' | head -n 1)"
BRIDGE="${BRIDGE:-vmbr0}"
if [[ -n "${CT_IP:-}" ]]; then
  # Host is often 192.168.14.1/24 while the CT is still 192.168.13.13.
  # They share vmbr0, so a /32 on the bridge lets the host reach the CT.
  ip route replace "${CT_IP}/32" dev "$BRIDGE" 2>/dev/null || true
fi

HOST_IP="$(ip -4 -o addr show dev "$BRIDGE" 2>/dev/null | awk '{print $4; exit}' | cut -d/ -f1)"
if [[ -z "$HOST_IP" ]]; then
  HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi

PUBLIC_URL="http://${HOST_IP}:${HOST_PORT}"
if pct exec "$CTID" -- test -f /etc/receiptvault/receiptvault.env; then
  pct exec "$CTID" -- bash -lc "ENV=/etc/receiptvault/receiptvault.env
grep -q '^RECEIPTVAULT_PUBLIC_URL=' \"\$ENV\" \
  && sed -i 's|^RECEIPTVAULT_PUBLIC_URL=.*|RECEIPTVAULT_PUBLIC_URL=${PUBLIC_URL}|' \"\$ENV\" \
  || echo RECEIPTVAULT_PUBLIC_URL=${PUBLIC_URL} >>\"\$ENV\""
  pct exec "$CTID" -- systemctl restart receiptvault || true
  sleep 2
fi

mkdir -p /usr/local/sbin /etc
printf '%s\n' "${CT_IP}" >/etc/receiptvault-proxy.target
printf '%s\n' "${HOST_PORT}" >/etc/receiptvault-proxy.port
cat >/usr/local/sbin/receiptvault-proxy.py <<'PY'
#!/usr/bin/python3
import pathlib
import socket
import threading

dest_ip = pathlib.Path("/etc/receiptvault-proxy.target").read_text().strip()
dest_port = 80
listen_port = int(pathlib.Path("/etc/receiptvault-proxy.port").read_text().strip() or "8484")


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
    try:
        client.close()
    except OSError:
        pass
    try:
        upstream.close()
    except OSError:
        pass


sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", listen_port))
sock.listen(64)
print(f"proxy 0.0.0.0:{listen_port} -> {dest_ip}:{dest_port}", flush=True)
while True:
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

# Let LAN browsers reach the proxy even if the host firewall is on.
if command -v iptables >/dev/null; then
  iptables -C INPUT -p tcp --dport "$HOST_PORT" -j ACCEPT 2>/dev/null \
    || iptables -I INPUT -p tcp --dport "$HOST_PORT" -j ACCEPT || true
fi
sleep 1

URL="http://${HOST_IP}:${HOST_PORT}/"
CODE="$(curl -sS -o /tmp/rv-host-body -w '%{http_code}' --connect-timeout 5 "$URL" || echo 000)"
echo "Host proxy ${URL} -> HTTP ${CODE}"
head -c 200 /tmp/rv-host-body 2>/dev/null; echo

if [[ "$CODE" != "200" ]]; then
  echo "Trying the container IP directly after adding a host route."
  DIRECT="$(curl -sS -o /tmp/rv-ct-body -w '%{http_code}' --connect-timeout 5 "http://${CT_IP}/" || echo 000)"
  echo "http://${CT_IP}/ -> HTTP ${DIRECT}"
  echo "Proxy did not return the app. journalctl -u receiptvault-proxy -n 20"
  journalctl -u receiptvault-proxy -n 20 --no-pager || true
  exit 1
fi

if [[ -f /root/ReceiptVault/deploy/install-host-command.sh ]]; then
  bash /root/ReceiptVault/deploy/install-host-command.sh || true
fi

echo
echo "Open this on the desktop (same IP as the Proxmox UI, different port):"
echo "  ${URL}"
echo "Do not use 192.168.13.13"
echo "Later updates on the host: receiptvault-update"
