# Shared IPv4 helpers for the Proxmox installer.
# shellcheck shell=bash

# LXC address the owner asked for. Gateway and prefix come from the host bridge.
PREFERRED_LXC_IP="${RECEIPTVAULT_LXC_IP:-192.168.13.14}"
DEFAULT_PREFIX="${RECEIPTVAULT_PREFIX:-20}"

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
      raw="$(python3 - "$raw" "$gw" "$DEFAULT_PREFIX" <<'PY'
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
gw = ipaddress.ip_address(sys.argv[2])
fallback = int(sys.argv[3])
for prefix in (24, 20, 16, 8):
    net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    if gw in net:
        print(f"{ip}/{prefix}")
        break
else:
    print(f"{ip}/{fallback}")
PY
)"
    else
      raw="${raw}/${DEFAULT_PREFIX}"
    fi
  fi
  if ! python3 -c "import ipaddress,sys; ipaddress.ip_interface(sys.argv[1])" "$raw" 2>/dev/null; then
    return 1
  fi
  printf '%s\n' "$raw"
}

ipv4_from_cidr() {
  printf '%s\n' "${1%%/*}"
}

guess_gateway_from_cidr() {
  local cidr="$1"
  local ip="${cidr%%/*}"
  printf '%s\n' "${ip%.*}.1"
}

host_bridge_cidr() {
  local br="$1"
  ip -4 -o addr show dev "$br" 2>/dev/null | awk '{print $4; exit}'
}

host_ipv4_on_bridge() {
  local cidr
  cidr="$(host_bridge_cidr "$1")" || true
  [[ -n "$cidr" ]] && printf '%s\n' "${cidr%%/*}"
}

suggest_static_cidr() {
  local bridge_cidr="$1"
  local want_host="${2:-14}"
  python3 - "$bridge_cidr" "$want_host" <<'PY'
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
  local network="$1"
  local address="$2"
  python3 - "$network" "$address" <<'PY'
import ipaddress, sys
net = ipaddress.ip_network(sys.argv[1], strict=False)
addr = ipaddress.ip_address(sys.argv[2].split("/")[0])
raise SystemExit(0 if addr in net else 1)
PY
}

# Prints: LXC_IP GATEWAY CIDR
# Prefers 192.168.13.14 on the host LAN. Uses the host prefix (/20 here).
# If the host iface is listed as /24 but 192.168.13.14 still shares a /20
# with the host, use 192.168.13.14/20 anyway.
choose_lxc_on_host_cidr() {
  local host_cidr="$1"
  local prefer="${2:-$PREFERRED_LXC_IP}"
  local fallback_prefix="${3:-$DEFAULT_PREFIX}"
  python3 - "$host_cidr" "$prefer" "$fallback_prefix" <<'PY'
import ipaddress, sys
iface = ipaddress.ip_interface(sys.argv[1])
prefer = ipaddress.ip_address(sys.argv[2])
fallback_prefix = int(sys.argv[3])
net = iface.network
host = iface.ip
if prefer in net and prefer != host and prefer != net.broadcast_address:
    print(f"{prefer} {host} {prefer}/{net.prefixlen}")
    raise SystemExit(0)
wide = ipaddress.ip_network(f"{prefer}/{fallback_prefix}", strict=False)
if host in wide and prefer != host:
    print(f"{prefer} {host} {prefer}/{fallback_prefix}")
    raise SystemExit(0)
candidate = ipaddress.ip_address(int(net.network_address) + 14)
if candidate not in net or candidate == host or candidate == net.broadcast_address:
    candidate = None
    for addr in net.hosts():
        if addr != host:
            candidate = addr
            break
if candidate is None:
    raise SystemExit(1)
print(f"{candidate} {host} {candidate}/{net.prefixlen}")
PY
}

detect_lan_on_bridge() {
  local br="${1:-vmbr0}"
  local cidr
  cidr="$(host_bridge_cidr "$br")" || return 1
  [[ -n "$cidr" ]] || return 1
  choose_lxc_on_host_cidr "$cidr"
}

public_url_for() {
  local ip="$1"
  local port="$2"
  if [[ "$port" == "80" ]]; then
    printf 'http://%s\n' "$ip"
  else
    printf 'http://%s:%s\n' "$ip" "$port"
  fi
}
