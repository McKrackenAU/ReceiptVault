# Install ReceiptVault on Proxmox VE

Helper-script style, same idea as the community Proxmox scripts: run **as root in the Proxmox shell**, answer a few `whiptail` screens, get an unprivileged Debian 13 LXC.

## 1. Source repository

Public GitHub source:

```text
https://github.com/McKrackenAU/ReceiptVault.git
```

If you need a fresh local copy on Windows, clone in **WSL** (Origin CLI is not available in PowerShell):

```bash
git clone https://github.com/McKrackenAU/ReceiptVault.git
```

## 2. Type this on the Proxmox host

**Safer (download, read, then run):**

```bash
wget -O /root/install-receiptvault.sh \
  https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/install-receiptvault.sh
less /root/install-receiptvault.sh
bash /root/install-receiptvault.sh
```

**Convenient one-liner (community-scripts style).** Inspect the URL first. Do **not** put mailbox passwords or tunnel tokens on this line:

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/install-receiptvault.sh)"
```

To install from a different fork:

```bash
RECEIPTVAULT_REPO=https://github.com/<FORK_USER>/ReceiptVault.git \
bash /root/install-receiptvault.sh
```

## 3. What the helper asks

Default install (same shape as other helper scripts):

1. Default / Advanced / Fix LAN IP / Repair / Update / Backup / Restore / Uninstall  
2. CTID, hostname, storage, disk  
3. **LXC IPv4** (default `192.168.13.13`)  
4. **Router / gateway** (default `192.168.1.1`)  
5. DNS (default `1.1.1.1`)  
6. Evidence storage  
7. Cloudflare: skip, existing tunnel, or paste a token into a password box (not logged)

Advanced adds CPU, RAM, bridge, DHCP, a custom browser port, and the git URL.

It then creates the LXC, installs PostgreSQL, Redis, OCR, builds the app, and prints:

```text
http://<the-ip-you-typed>/
```

Port 80 — no `:8082`. Create the owner account there.

To change an existing CT, re-run the helper and choose **Fix / change LAN IP**.

## 4. Install from a USB/SCP copy (no GitHub yet)

Copy this repository onto the Proxmox host, then:

```bash
cd /root/receiptvault
bash deploy/install-receiptvault.sh
```

The helper detects the local tree and copies it into the LXC instead of cloning.

## 5. If the UI is not reachable

On the Proxmox host:

```bash
wget -O /root/fix-receiptvault.sh \
  https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/fix-from-host.sh
bash /root/fix-receiptvault.sh
```

Then open **http://192.168.13.13/** (or the IP you entered). The LXC uses the gateway you entered for internet (mailbox scan).

## 6. After install

- Existing Cloudflare Tunnel origin: `http://<lxc-ip>/`
- Re-run the same helper and choose **Update**, **Repair**, **Backup**, or **Uninstall**
- Owner password reset from the host: `pct exec <CTID> -- receiptvault reset-password OWNER 'new-long-password'`
