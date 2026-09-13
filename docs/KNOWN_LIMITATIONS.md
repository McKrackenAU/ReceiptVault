# Known limitations (v1)

- Body-only HTML snapshots use Playwright Chromium when installed; otherwise ReportLab produces a text PDF so the app still starts without a browser.
- HEIC preview depends on `pillow-heif` being present on the host. Originals are still preserved.
- Incremental Graph delta queries are used when the mock/live client supplies a delta link; otherwise a high-water mark plus overlap is stored.
- Optional AI providers remain disabled (`RECEIPTVAULT_AI_ENABLED=false`). Classification is rule-based.
- The Proxmox installer expects `pct`/`pveam` on the host. Shell lint covers the script in CI-like environments without a live Proxmox cluster.
- Multi-gigabyte folder packages stream to disk; browsers that cannot use the File System Access API fall back to range-assembled downloads and should not keep the entire Blob if the operator uses `curl --range` or a download manager.
