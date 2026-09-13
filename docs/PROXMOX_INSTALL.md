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

Choose **Default install**. Accept `192.168.13.14` and the suggested gateway. Prefix is **/20**.

If the page will not load, run `bash deploy/reach.sh` on the host. That reapplies `192.168.13.14/20` and starts the app.

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
