# Shared IPv4 helpers for the Proxmox installer.
# shellcheck shell=bash

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

suggest_static_cidr() {
  local bridge_cidr="$1"
  local want_host="${2:-13}"
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

public_url_for() {
  local ip="$1"
  local port="$2"
  if [[ "$port" == "80" ]]; then
    printf 'http://%s\n' "$ip"
  else
    printf 'http://%s:%s\n' "$ip" "$port"
  fi
}
