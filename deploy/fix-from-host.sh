#!/usr/bin/env bash
# Run as root on the Proxmox HOST (the shell that has pct).
#
#   wget -O /root/fix-receiptvault.sh \
#     https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/fix-from-host.sh
#   bash /root/fix-receiptvault.sh
#
# Puts ReceiptVault on the LXC IP you already chose and serves
# http://<that-ip>/  (port 80, same as every other helper-script CT).
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8

if [[ ${EUID} -ne 0 ]] || ! command -v pct >/dev/null; then
  echo "Run as root on the Proxmox host (the shell that has pct)."
  exit 1
fi

CTID="${1:-}"
LXC_IP="${2:-192.168.13.13}"
LXC_GW="${3:-${RECEIPTVAULT_GATEWAY:-192.168.1.1}}"
BRIDGE="${RECEIPTVAULT_BRIDGE:-vmbr0}"
DNS="${RECEIPTVAULT_DNS:-1.1.1.1}"

# Same rule as the installer: pick a prefix that contains both the IP and the gateway.
LXC_CIDR="$(python3 - "$LXC_IP" "$LXC_GW" <<'PY'
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

CTID="$(find_ct "$CTID" || true)"
if [[ -z "$CTID" ]]; then
  echo "No ReceiptVault CT found."
  pct list
  echo "Usage: bash $0 <CTID> <IPv4> <gateway>"
  exit 1
fi

echo "CT ${CTID}  ->  http://${LXC_IP}/   gateway ${LXC_GW}  (${LXC_CIDR} on ${BRIDGE})"

systemctl disable --now receiptvault-forward.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/receiptvault-forward.service /usr/local/sbin/receiptvault-forward.sh
systemctl daemon-reload >/dev/null 2>&1 || true

if ! pct status "$CTID" | grep -q running; then
  pct start "$CTID"
  sleep 3
fi

pct set "$CTID" --firewall 0 >/dev/null || true
pct set "$CTID" --onboot 1 >/dev/null || true
pct set "$CTID" --net0 "name=eth0,bridge=${BRIDGE},firewall=0,ip=${LXC_CIDR},gw=${LXC_GW}"
pct set "$CTID" --nameserver "$DNS" >/dev/null || true

for _ in $(seq 1 30); do
  pct exec "$CTID" -- true >/dev/null 2>&1 && break
  sleep 1
done

echo "Setting ${LXC_CIDR} via ${LXC_GW} inside the LXC"
pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  RV_CIDR="$LXC_CIDR" RV_GATEWAY="$LXC_GW" RV_DNS="$DNS" bash -s <<'EOS'
set -euo pipefail
IFACE=eth0
CIDR="$RV_CIDR"
GW="$RV_GATEWAY"
ADDR="${CIDR%%/*}"
cat >/etc/network/interfaces <<EOF
auto lo
iface lo inet loopback

auto ${IFACE}
iface ${IFACE} inet static
    address ${CIDR}
    gateway ${GW}
    dns-nameservers ${RV_DNS}
EOF
printf 'nameserver %s\n' "$RV_DNS" >/etc/resolv.conf
sysctl -w net.ipv4.ip_unprivileged_port_start=0 >/dev/null 2>&1 || true
mkdir -p /etc/sysctl.d
echo 'net.ipv4.ip_unprivileged_port_start=0' >/etc/sysctl.d/20-receiptvault-ports.conf
ip link set "$IFACE" up || true
ip addr flush dev "$IFACE" 2>/dev/null || true
ip addr add "$CIDR" dev "$IFACE"
ip route replace default via "$GW" dev "$IFACE" 2>/dev/null || true
ip -4 addr show dev "$IFACE"
ip route
EOS

if ! pct exec "$CTID" -- test -d /opt/receiptvault/backend; then
  echo "This CT has no /opt/receiptvault. The first install did not finish."
  echo "Re-run the helper installer (Default install) and enter this IP when asked."
  exit 1
fi

echo "Stopping Caddy; serving ReceiptVault on http://${LXC_IP}/"
pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  RV_IP="$LXC_IP" bash -s <<'EOS'
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:$PATH"
APP=/opt/receiptvault
ENV=/etc/receiptvault/receiptvault.env
IP="$RV_IP"
PUBLIC="http://${IP}"

systemctl disable --now caddy >/dev/null 2>&1 || true
systemctl mask caddy >/dev/null 2>&1 || true
fuser -k 80/tcp >/dev/null 2>&1 || true

id receiptvault >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin receiptvault
chown -R receiptvault:receiptvault "$APP" /var/lib/receiptvault 2>/dev/null || true

if [[ ! -x "$APP/backend/.venv/bin/uvicorn" ]]; then
  echo "Installing Python env (a few minutes)"
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
  cd "$APP/backend"
  runuser -u receiptvault -- env PATH="$PATH" uv sync --frozen --no-dev || \
    runuser -u receiptvault -- env PATH="$PATH" uv sync --no-dev
fi
if [[ ! -f "$APP/frontend/dist/index.html" ]]; then
  echo "Building UI (a few minutes)"
  cd "$APP/frontend"
  if [[ -f package-lock.json ]]; then
    runuser -u receiptvault -- env PATH="$PATH" npm ci
  else
    runuser -u receiptvault -- env PATH="$PATH" npm install
  fi
  runuser -u receiptvault -- env PATH="$PATH" npm run build
fi

if [[ ! -f "$ENV" ]]; then
  echo "Missing $ENV — re-run the helper installer once so secrets exist."
  exit 1
fi
grep -q '^RECEIPTVAULT_PUBLIC_URL=' "$ENV" && sed -i "s|^RECEIPTVAULT_PUBLIC_URL=.*|RECEIPTVAULT_PUBLIC_URL=${PUBLIC}|" "$ENV" || echo "RECEIPTVAULT_PUBLIC_URL=${PUBLIC}" >>"$ENV"
grep -q '^RECEIPTVAULT_LAN_PORT=' "$ENV" && sed -i "s|^RECEIPTVAULT_LAN_PORT=.*|RECEIPTVAULT_LAN_PORT=8082|" "$ENV" || echo "RECEIPTVAULT_LAN_PORT=8082" >>"$ENV"
grep -q '^RECEIPTVAULT_API_HOST=' "$ENV" && sed -i "s|^RECEIPTVAULT_API_HOST=.*|RECEIPTVAULT_API_HOST=0.0.0.0|" "$ENV" || echo "RECEIPTVAULT_API_HOST=0.0.0.0" >>"$ENV"
grep -q '^RECEIPTVAULT_API_PORT=' "$ENV" && sed -i "s|^RECEIPTVAULT_API_PORT=.*|RECEIPTVAULT_API_PORT=8082|" "$ENV" || echo "RECEIPTVAULT_API_PORT=8082" >>"$ENV"

mkdir -p "$APP/deploy"
cat >"$APP/deploy/run-api.sh" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/receiptvault/backend
exec /opt/receiptvault/backend/.venv/bin/uvicorn app.main:app \
  --host "${RECEIPTVAULT_API_HOST:-0.0.0.0}" \
  --port "${RECEIPTVAULT_API_PORT:-${RECEIPTVAULT_LAN_PORT:-8082}}"
RUN
chmod 0755 "$APP/deploy/run-api.sh"

cat >"$APP/deploy/lan-http80.sh" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
PORT="${RECEIPTVAULT_API_PORT:-${RECEIPTVAULT_LAN_PORT:-8082}}"
export RV_HTTP80_TARGET="$PORT"
exec python3 - <<'PY'
import os, socket, threading
target = int(os.environ["RV_HTTP80_TARGET"])
def pump(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listen.bind(("0.0.0.0", 80))
listen.listen(128)
while True:
    client, _ = listen.accept()
    try:
        upstream = socket.create_connection(("127.0.0.1", target), timeout=10)
    except OSError:
        client.close()
        continue
    threading.Thread(target=pump, args=(client, upstream), daemon=True).start()
    threading.Thread(target=pump, args=(upstream, client), daemon=True).start()
PY
RUN
chmod 0755 "$APP/deploy/lan-http80.sh"

cat >/etc/systemd/system/receiptvault.service <<'UNIT'
[Unit]
Description=ReceiptVault
After=network.target postgresql.service redis-server.service
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

cat >/etc/systemd/system/receiptvault-http80.service <<'UNIT'
[Unit]
Description=ReceiptVault HTTP port 80
After=receiptvault.service
Wants=receiptvault.service
[Service]
Type=simple
EnvironmentFile=-/etc/receiptvault/receiptvault.env
ExecStart=/opt/receiptvault/deploy/lan-http80.sh
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now postgresql redis-server >/dev/null 2>&1 || true
systemctl restart postgresql redis-server || true
set -a
# shellcheck disable=SC1090
source "$ENV"
set +a
if [[ -f "$APP/deploy/ensure-db.sh" ]]; then
  bash "$APP/deploy/ensure-db.sh"
else
  python3 - <<'PY'
import os, subprocess, urllib.parse
raw = os.environ.get("RECEIPTVAULT_DATABASE_URL", "")
url = raw.replace("postgresql+psycopg://", "postgresql://", 1)
parsed = urllib.parse.urlparse(url)
user = urllib.parse.unquote(parsed.username or "receiptvault")
password = urllib.parse.unquote(parsed.password or "")
database = (parsed.path or "/receiptvault").lstrip("/") or "receiptvault"
pw = password.replace("'", "''")
def psql(*args):
    subprocess.run(["runuser", "-u", "postgres", "--", "psql", "-v", "ON_ERROR_STOP=1", *args], check=True)
psql("-c", f"DO $$ BEGIN CREATE ROLE {user} LOGIN PASSWORD '{pw}'; EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
psql("-c", f"ALTER ROLE {user} WITH LOGIN PASSWORD '{pw}';")
exists = subprocess.run(
    ["runuser", "-u", "postgres", "--", "psql", "-tAc", f"SELECT 1 FROM pg_database WHERE datname = '{database}'"],
    check=True, capture_output=True, text=True,
).stdout.strip()
if exists != "1":
    psql("-c", f"CREATE DATABASE {database} OWNER {user};")
psql("-d", database, "-c", f"GRANT ALL ON SCHEMA public TO {user}; ALTER DATABASE {database} OWNER TO {user};")
print("database ready")
PY
fi
systemctl enable receiptvault receiptvault-http80 >/dev/null
systemctl restart receiptvault
systemctl restart receiptvault-http80

ok=0
for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:80/health/live" >/dev/null 2>&1 && ok=1 && break
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  journalctl -u receiptvault -u receiptvault-http80 -n 50 --no-pager || true
  ss -lntp || true
  exit 1
fi
echo "App is up on http://${IP}/"
EOS

echo
echo "==== From inside the LXC ===="
pct exec "$CTID" -- bash -lc "ss -lntp | grep -E ':80 |:8082' || true; curl -sS -o /dev/null -w 'local http://127.0.0.1/  %{http_code}\n' http://127.0.0.1/health/live || true"
echo "==== From the Proxmox host ===="
CODE="$(curl -sS -o /tmp/rv-fix-body -w '%{http_code}' --connect-timeout 5 "http://${LXC_IP}/" || echo 000)"
echo "http://${LXC_IP}/  -> HTTP ${CODE}"
head -c 200 /tmp/rv-fix-body 2>/dev/null; echo

if [[ "$CODE" != "200" ]]; then
  echo "Host could not open http://${LXC_IP}/ — container net:"
  pct exec "$CTID" -- ip -4 addr
  pct exec "$CTID" -- ip route
  pct exec "$CTID" -- journalctl -u receiptvault -u receiptvault-http80 -n 30 --no-pager || true
  exit 1
fi

echo
echo "Open this in the browser (no port number):"
echo "  http://${LXC_IP}/"
