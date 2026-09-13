#!/usr/bin/env bash
# Run as root on the Proxmox HOST (the shell that has pct).
# First time on the Proxmox host, type these three short lines:
#
#   cd /root
#   git clone --depth 1 https://github.com/McKrackenAU/ReceiptVault.git
#   bash /root/ReceiptVault/deploy/fix-from-host.sh
#
# After that, type: receiptvault-update
#
# Downloads ReceiptVault from GitHub on the HOST, unpacks it in the LXC,
# purges Caddy, and binds the app on http://<lxc-ip>/
echo "ReceiptVault 1.5.0 — refresh app from GitHub, purge Caddy, bind :80"
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive

if [[ ${EUID} -ne 0 ]] || ! command -v pct >/dev/null; then
  echo "Run as root on the Proxmox host (the shell that has pct)."
  exit 1
fi

CTID="${1:-}"
LXC_IP="${2:-192.168.13.13}"
LXC_GW="${3:-${RECEIPTVAULT_GATEWAY:-192.168.1.1}}"
BRIDGE="${RECEIPTVAULT_BRIDGE:-vmbr0}"
DNS="${RECEIPTVAULT_DNS:-1.1.1.1}"

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

nuke_caddy_guest() {
  local id="$1"
  pct status "$id" 2>/dev/null | grep -q running || return 0
  echo "  purging Caddy in CT ${id}"
  pct exec "$id" -- env DEBIAN_FRONTEND=noninteractive bash -lc '
    systemctl disable --now caddy.service caddy.socket >/dev/null 2>&1 || true
    systemctl mask caddy.service caddy.socket >/dev/null 2>&1 || true
    pkill -9 caddy >/dev/null 2>&1 || true
    fuser -k 80/tcp >/dev/null 2>&1 || true
    apt-get purge -y caddy >/dev/null 2>&1 || dpkg --purge caddy >/dev/null 2>&1 || true
    rm -rf /etc/caddy /usr/share/caddy /var/lib/caddy
    rm -f /usr/bin/caddy /usr/local/bin/caddy
    apt-mark hold caddy >/dev/null 2>&1 || true
  ' || true
}

echo "Looking for anything else that already owns ${LXC_IP} or is running Caddy"
if ip -4 addr show | grep -q "inet ${LXC_IP}/"; then
  echo "  this Proxmox host has ${LXC_IP} — removing that address from the host"
  ip -4 addr show | awk '/inet '"${LXC_IP}"'\// {print $2}' | while read -r cidr; do
    iface="$(ip -4 -o addr show | awk -v c="$cidr" '$4==c {print $2; exit}')"
    [[ -n "$iface" ]] && ip addr del "$cidr" dev "$iface" || true
  done
fi
systemctl disable --now caddy.service caddy.socket >/dev/null 2>&1 || true
pkill -9 caddy >/dev/null 2>&1 || true

while read -r id name; do
  [[ -z "$id" ]] && continue
  conf="/etc/pve/lxc/${id}.conf"
  has=0
  if [[ -f "$conf" ]] && grep -q "${LXC_IP}" "$conf"; then
    has=1
  fi
  if pct status "$id" 2>/dev/null | grep -q running; then
    if pct exec "$id" -- bash -lc "ip -4 addr show | grep -q 'inet ${LXC_IP}/'" 2>/dev/null; then
      has=1
    fi
    if pct exec "$id" -- bash -lc 'pgrep -x caddy >/dev/null || command -v caddy >/dev/null' 2>/dev/null; then
      echo "  CT ${id} (${name}) has a Caddy binary/process"
      nuke_caddy_guest "$id"
    fi
  fi
  if [[ "$has" -eq 1 && "$id" != "$CTID" ]]; then
    echo "  CT ${id} (${name}) is configured with ${LXC_IP} — taking that address off it"
    nuke_caddy_guest "$id"
    net0="$(pct config "$id" 2>/dev/null | sed -n 's/^net0: //p' || true)"
    if [[ -n "$net0" && "$net0" == *"${LXC_IP}"* ]]; then
      new="$(printf '%s\n' "$net0" | sed -E "s/ip=${LXC_IP}\/[0-9]+/ip=dhcp/")"
      pct set "$id" --net0 "$new" || true
    fi
  fi
done < <(pct list | awk 'NR>1 {print $1, $3}')

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

echo "Setting ${LXC_CIDR} via ${LXC_GW}"
pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  RV_CIDR="$LXC_CIDR" RV_GATEWAY="$LXC_GW" RV_DNS="$DNS" bash -s <<'EOS'
set -euo pipefail
IFACE=eth0
CIDR="$RV_CIDR"
GW="$RV_GATEWAY"
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
EOS

if ! pct exec "$CTID" -- test -d /opt/receiptvault/backend; then
  echo "This CT has no /opt/receiptvault. Re-run the helper installer."
  exit 1
fi

echo "Install ReceiptVault 1.5.0 (this is what actually changes the version)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || true)"
LOCAL=""
if [[ -n "$SCRIPT_DIR" && -d "$SCRIPT_DIR/../backend" && -d "$SCRIPT_DIR/../frontend" ]]; then
  LOCAL="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
if [[ -n "$LOCAL" ]]; then
  echo "Copying local tree $LOCAL into CT ${CTID}"
  tar -C "$LOCAL" --exclude='.git' --exclude='node_modules' --exclude='frontend/node_modules' --exclude='.venv' --exclude='backend/.venv' --exclude='var' -cf - . \
    | pct exec "$CTID" -- tar -C /opt/receiptvault -xf -
else
  echo "Downloading source (IPv4, 40s timeout)..."
  TGZ=/tmp/receiptvault-main.tgz
  wget -4 --timeout=40 --tries=3 -nv --no-cache -O "$TGZ" https://github.com/McKrackenAU/ReceiptVault/archive/refs/heads/main.tar.gz
  echo "Download finished."
  if ! gzip -t "$TGZ" 2>/dev/null; then
    echo "ERROR: GitHub download was not a gzip archive. First bytes:"
    head -c 200 "$TGZ"; echo
    exit 1
  fi
  pct push "$CTID" "$TGZ" /tmp/receiptvault-main.tgz
  pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 bash -s <<'EOS'
set -euo pipefail
APP=/opt/receiptvault
rm -rf /tmp/ReceiptVault-main
tar -xzf /tmp/receiptvault-main.tgz -C /tmp
SRC="$(find /tmp -maxdepth 1 -type d -name 'ReceiptVault-*' | head -n 1)"
test -d "$SRC/backend"
cp -a "$SRC/." "$APP/"
rm -rf "$SRC" /tmp/receiptvault-main.tgz
EOS
fi
pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 bash -s <<'EOS'
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:$PATH"
export DEBIAN_FRONTEND=noninteractive
APP=/opt/receiptvault
id receiptvault >/dev/null 2>&1 && chown -R receiptvault:receiptvault "$APP/frontend" "$APP/backend/app" "$APP/deploy" || true
chmod +x "$APP/deploy/"*.sh "$APP/deploy/run-api.sh" 2>/dev/null || true
command -v npm >/dev/null || apt-get install -y -qq npm >/dev/null
echo "Building UI (a few minutes)"
cd "$APP/frontend"
if [[ -f package-lock.json ]]; then
  npm ci --omit=optional || npm install --omit=optional
else
  npm install --omit=optional
fi
npx vite build
chmod -R a+rX "$APP/frontend/dist"
if [[ ! -f "$APP/frontend/dist/index.html" ]]; then
  echo "ERROR: UI build did not produce frontend/dist/index.html"
  exit 1
fi
echo "Unpacked ReceiptVault 1.5.0"
EOS

echo "Purging Caddy and binding ReceiptVault on port 80"
pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  RV_IP="$LXC_IP" bash -s <<'EOS'
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:$PATH"
export DEBIAN_FRONTEND=noninteractive
APP=/opt/receiptvault
ENV=/etc/receiptvault/receiptvault.env
IP="$RV_IP"
PUBLIC="http://${IP}"

systemctl disable --now caddy.service caddy.socket receiptvault-http80.service >/dev/null 2>&1 || true
systemctl mask caddy.service caddy.socket >/dev/null 2>&1 || true
pkill -9 caddy >/dev/null 2>&1 || true
fuser -k 80/tcp >/dev/null 2>&1 || true
apt-get purge -y caddy >/dev/null 2>&1 || dpkg --purge caddy >/dev/null 2>&1 || true
rm -rf /etc/caddy /usr/share/caddy /var/lib/caddy
rm -f /usr/bin/caddy /usr/local/bin/caddy
apt-mark hold caddy >/dev/null 2>&1 || true
systemctl daemon-reload >/dev/null 2>&1 || true

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
grep -q '^RECEIPTVAULT_LAN_PORT=' "$ENV" && sed -i "s|^RECEIPTVAULT_LAN_PORT=.*|RECEIPTVAULT_LAN_PORT=80|" "$ENV" || echo "RECEIPTVAULT_LAN_PORT=80" >>"$ENV"
grep -q '^RECEIPTVAULT_API_HOST=' "$ENV" && sed -i "s|^RECEIPTVAULT_API_HOST=.*|RECEIPTVAULT_API_HOST=0.0.0.0|" "$ENV" || echo "RECEIPTVAULT_API_HOST=0.0.0.0" >>"$ENV"
grep -q '^RECEIPTVAULT_API_PORT=' "$ENV" && sed -i "s|^RECEIPTVAULT_API_PORT=.*|RECEIPTVAULT_API_PORT=80|" "$ENV" || echo "RECEIPTVAULT_API_PORT=80" >>"$ENV"
grep -q '^RECEIPTVAULT_APP_VERSION=' "$ENV" && sed -i "s|^RECEIPTVAULT_APP_VERSION=.*|RECEIPTVAULT_APP_VERSION=1.5.0|" "$ENV" || echo "RECEIPTVAULT_APP_VERSION=1.5.0" >>"$ENV"

mkdir -p "$APP/deploy"
cat >"$APP/deploy/run-api.sh" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/receiptvault/backend
exec /opt/receiptvault/backend/.venv/bin/uvicorn app.main:app \
  --host "${RECEIPTVAULT_API_HOST:-0.0.0.0}" \
  --port "${RECEIPTVAULT_API_PORT:-${RECEIPTVAULT_LAN_PORT:-80}}"
RUN
chmod 0755 "$APP/deploy/run-api.sh"

cat >/etc/systemd/system/receiptvault.service <<'UNIT'
[Unit]
Description=ReceiptVault
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service
[Service]
Type=simple
User=root
Group=root
EnvironmentFile=/etc/receiptvault/receiptvault.env
WorkingDirectory=/opt/receiptvault/backend
ExecStart=/opt/receiptvault/deploy/run-api.sh
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
systemctl disable --now receiptvault-http80.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/receiptvault-http80.service

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

fuser -k 80/tcp >/dev/null 2>&1 || true
systemctl enable receiptvault >/dev/null
systemctl restart receiptvault

ok=0
for _ in $(seq 1 40); do
  body="$(curl -fsS http://127.0.0.1/health/live 2>/dev/null || true)"
  if [[ "$body" == *ok* ]]; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  journalctl -u receiptvault -n 60 --no-pager || true
  ss -lntp || true
  exit 1
fi

page="$(curl -fsS http://127.0.0.1/ 2>/dev/null || true)"
if echo "$page" | grep -qi 'Your web server is working'; then
  echo "Port 80 is still the Caddy welcome page."
  ss -lntp || true
  exit 1
fi
echo "App is up on http://${IP}/  version 1.5.0"
EOS

echo
echo "==== From inside the LXC ===="
pct exec "$CTID" -- bash -lc 'ss -lntp | grep -E ":80 |caddy|uvicorn" || true; echo -n "health: "; curl -sS http://127.0.0.1/health/live; echo'
echo "==== From the Proxmox host ===="
CODE="$(curl -sS -o /tmp/rv-fix-body -w '%{http_code}' --connect-timeout 5 "http://${LXC_IP}/" || echo 000)"
echo "http://${LXC_IP}/  -> HTTP ${CODE}"
head -c 240 /tmp/rv-fix-body 2>/dev/null; echo

if [[ "$CODE" != "200" ]] || grep -qi 'Your web server is working\|Congratulations' /tmp/rv-fix-body 2>/dev/null; then
  echo "Host did not get the ReceiptVault page from http://${LXC_IP}/"
  pct exec "$CTID" -- bash -lc 'command -v caddy; dpkg -l caddy 2>/dev/null | tail -1; ss -lntp; journalctl -u receiptvault -n 40 --no-pager' || true
  exit 1
fi

if [[ -f "$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd)/install-host-command.sh" ]]; then
  bash "$(cd "$(dirname "${BASH_SOURCE[0]:-}")" && pwd)/install-host-command.sh" || true
else
  install -m 0755 /dev/stdin /usr/local/sbin/receiptvault-update <<'WRAP' || true
#!/bin/bash
echo "ReceiptVault host update"
set -euo pipefail
command -v git >/dev/null || apt-get install -y -qq git
if [[ -d /root/ReceiptVault/.git ]]; then
  git -C /root/ReceiptVault fetch --depth 1 origin main
  git -C /root/ReceiptVault reset --hard origin/main
else
  rm -rf /root/ReceiptVault
  git clone --depth 1 https://github.com/McKrackenAU/ReceiptVault.git /root/ReceiptVault
fi
exec bash /root/ReceiptVault/deploy/fix-from-host.sh "$@"
WRAP
fi
echo
echo "Open this in the browser (no port number):"
echo "  http://${LXC_IP}/"
echo "Hard-refresh the tab (Ctrl+Shift+R)."
echo "Settings must show 1.5.0."
echo "Next update, type this on the Proxmox host:"
echo "  receiptvault-update"
