#!/usr/bin/env bash
# Apply a static IPv4 address inside the ReceiptVault LXC.
# Env: RV_CIDR=192.168.14.13/24 RV_GATEWAY=192.168.14.1 RV_DNS=1.1.1.1 RV_IFACE=eth0
set -euo pipefail
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

IFACE="${RV_IFACE:-eth0}"
CIDR="${RV_CIDR:-}"
GATEWAY="${RV_GATEWAY:-}"
DNS="${RV_DNS:-1.1.1.1}"

if [[ -z "$CIDR" ]]; then
  echo "RV_CIDR is required (for example 192.168.14.13/24)" >&2
  exit 1
fi
if [[ "$CIDR" != */* ]]; then
  CIDR="${CIDR}/24"
fi
ADDR="${CIDR%%/*}"

python3 -c "import ipaddress,sys; ipaddress.ip_interface(sys.argv[1])" "$CIDR"

mkdir -p /etc/network
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

# Allow Caddy to bind :80 in an unprivileged LXC.
if [[ -d /proc/sys/net/ipv4 ]]; then
  sysctl -w net.ipv4.ip_unprivileged_port_start=0 >/dev/null 2>&1 || true
  mkdir -p /etc/sysctl.d
  echo 'net.ipv4.ip_unprivileged_port_start=0' >/etc/sysctl.d/20-receiptvault-ports.conf
fi

bring_up() {
  ip link set "$IFACE" up || true
  if ip -4 addr show dev "$IFACE" | grep -q "inet ${ADDR}/"; then
    return 0
  fi
  ip addr flush dev "$IFACE" 2>/dev/null || true
  ip addr add "$CIDR" dev "$IFACE"
}

if command -v ifup >/dev/null 2>&1; then
  ifdown "$IFACE" >/dev/null 2>&1 || true
  ifup "$IFACE" >/dev/null 2>&1 || bring_up
else
  bring_up
fi

if [[ -n "$GATEWAY" ]]; then
  ip route replace default via "$GATEWAY" dev "$IFACE" 2>/dev/null || \
    ip route add default via "$GATEWAY" dev "$IFACE" 2>/dev/null || true
fi

if ! ip -4 addr show dev "$IFACE" | grep -q "inet ${ADDR}/"; then
  echo "Failed to assign ${CIDR} on ${IFACE}" >&2
  ip addr show >&2 || true
  exit 1
fi

echo "NETWORK_OK ${CIDR} via ${GATEWAY:-none}"
