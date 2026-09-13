#!/usr/bin/env bash
# Apply 192.168.13.14/20 (or RV_CIDR) inside the LXC with ip(8) only.
# Bouncing the NIC with Debian interface scripts drops LAN traffic.
# Env: RV_CIDR=192.168.13.14/20 RV_GATEWAY=<bridge-ip> RV_DNS=1.1.1.1 RV_IFACE=eth0
set -euo pipefail
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

IFACE="${RV_IFACE:-eth0}"
CIDR="${RV_CIDR:-}"
GATEWAY="${RV_GATEWAY:-}"
DNS="${RV_DNS:-1.1.1.1}"

if [[ -z "$CIDR" ]]; then
  echo "RV_CIDR is required (for example 192.168.13.14/20)" >&2
  exit 1
fi
if [[ "$CIDR" != */* ]]; then
  CIDR="${CIDR}/20"
fi
ADDR="${CIDR%%/*}"

python3 -c "import ipaddress,sys; ipaddress.ip_interface(sys.argv[1])" "$CIDR"

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

if [[ -n "$DNS" ]]; then
  printf 'nameserver %s\n' "$DNS" >/etc/resolv.conf
fi

if [[ -d /proc/sys/net/ipv4 ]]; then
  sysctl -w net.ipv4.ip_unprivileged_port_start=0 >/dev/null 2>&1 || true
  echo 'net.ipv4.ip_unprivileged_port_start=0' >/etc/sysctl.d/20-receiptvault-ports.conf
fi

ip link set "$IFACE" up || true

# Must match the full CIDR. "inet 192.168.13.14/24" must not count as /20.
current="$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{print $4}')"
if ! printf '%s\n' "$current" | grep -qx "$CIDR"; then
  while read -r old; do
    [[ -z "$old" ]] && continue
    [[ "$old" == "$CIDR" ]] && continue
    [[ "$old" == "${ADDR}/"* ]] && ip addr del "$old" dev "$IFACE" 2>/dev/null || true
  done <<< "$current"
  ip addr add "$CIDR" dev "$IFACE"
fi

if [[ -n "$GATEWAY" ]]; then
  ip route replace default via "$GATEWAY" dev "$IFACE" 2>/dev/null || \
    ip route add default via "$GATEWAY" dev "$IFACE" 2>/dev/null || true
fi

assigned="$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{print $4}')"
if ! printf '%s\n' "$assigned" | grep -qx "$CIDR"; then
  echo "Failed to assign ${CIDR} on ${IFACE}" >&2
  ip addr show >&2 || true
  exit 1
fi

echo "NETWORK_OK ${CIDR} via ${GATEWAY:-none}"
echo "$assigned"
ip route show default || true
