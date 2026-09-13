# Install ReceiptVault on Proxmox VE

Run as root in the Proxmox shell. This is a **Default install** (new CT).

## Type this

```bash
cd /root/ReceiptVault
git pull
bash deploy/install-receiptvault.sh
```

If `/root/ReceiptVault` is missing:

```bash
git clone --depth 1 https://github.com/McKrackenAU/ReceiptVault.git /root/ReceiptVault
bash /root/ReceiptVault/deploy/install-receiptvault.sh
```

Choose **Default install**. Accept the suggested LXC IPv4 (`192.168.13.14`) and the suggested gateway (this host's address on vmbr0). The LAN prefix is taken from the host bridge (`/20` on this network).

## Open the app

On the desktop, open:

**http://192.168.13.14/**

Hard-refresh (Ctrl+Shift+R). Settings must show **1.5.1**.

Create the owner, save the Entra app in Settings, connect Hotmail with the Microsoft device code, start the historical scan.

## Later updates

Same three lines, then choose **Update**. Or type `receiptvault-update` on the host.

## Owner password reset

```bash
pct exec 200 -- receiptvault reset-password OWNER 'new-long-password'
```
