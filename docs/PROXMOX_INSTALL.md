# Install ReceiptVault on Proxmox VE

Run as root in the Proxmox shell.

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

Choose **Update** for an existing CT, or **Default install** for a new one. If it asks for IPv4 / gateway, use an address on the **same LAN as the Proxmox UI** (if Proxmox is `https://192.168.14.1:8006`, use `192.168.14.13` and `192.168.14.1`).

## Open the app

On the desktop, open:

**http://192.168.14.1:8484/**

That is the same IP as the Proxmox UI, port 8484. Do not open `192.168.13.13`. Hard-refresh (Ctrl+Shift+R). Settings must show **1.5.1**.

Create the owner, save the Entra app in Settings, connect Hotmail with the Microsoft device code, start the historical scan.

## Later updates

Same three lines: `cd /root/ReceiptVault`, `git pull`, `bash deploy/install-receiptvault.sh`, then choose **Update**. Or type `receiptvault-update` on the host.

## Owner password reset

```bash
pct exec 200 -- receiptvault reset-password OWNER 'new-long-password'
```
