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

1. Default / Advanced / Repair / Update / Backup / Restore / Uninstall  
2. CTID, hostname, storage, disk  
3. Advanced only: CPU, RAM, bridge, DHCP or static IP, unprivileged toggle, git URL  
4. Evidence storage: LXC disk, new host bind mount, or existing NFS/host path  
5. LAN port (default **8080**)  
6. Cloudflare: skip, existing tunnel, or paste a tunnel token into a password box (not logged)

It then creates the LXC, installs PostgreSQL, Redis, Caddy, OCR, builds the app, enables systemd, and prints:

```text
http://<lxc-ip>:8080
```

Create the owner account there. No source edits.

## 4. Install from a USB/SCP copy (no GitHub yet)

Copy this repository onto the Proxmox host, then:

```bash
cd /root/receiptvault
bash deploy/install-receiptvault.sh
```

The helper detects the local tree and copies it into the LXC instead of cloning.

## 5. After install

- Existing Cloudflare Tunnel origin: `http://<lxc-ip>:8080`
- Re-run the same helper and choose **Update**, **Repair**, **Backup**, or **Uninstall**
- Owner password reset from the host: `pct exec <CTID> -- receiptvault reset-password OWNER 'new-long-password'`
