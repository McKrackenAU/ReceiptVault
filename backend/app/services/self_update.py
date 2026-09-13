from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

APP_VERSION = "1.5.0"
DEFAULT_TARBALL = "https://github.com/McKrackenAU/ReceiptVault/archive/refs/heads/main.tar.gz"
DEFAULT_ROOT = Path("/opt/receiptvault")


def app_root() -> Path:
    return Path(os.environ.get("RECEIPTVAULT_APP_ROOT", str(DEFAULT_ROOT)))


def production_install(root: Path | None = None) -> bool:
    root = root or app_root()
    return (root / "backend").is_dir() and (root / "frontend").is_dir()


def apply_update(
    *,
    root: Path | None = None,
    tarball_url: str | None = None,
    skip_frontend: bool = False,
    skip_restart: bool = False,
    archive: Path | None = None,
) -> dict[str, str]:
    root = root or app_root()
    if not production_install(root):
        raise RuntimeError(f"Not a ReceiptVault install: {root}")

    work = Path(tempfile.mkdtemp(prefix="receiptvault-update-"))
    tgz = archive or (work / "main.tar.gz")
    try:
        if archive is None:
            url = tarball_url or os.environ.get("RECEIPTVAULT_TARBALL_URL", DEFAULT_TARBALL)
            urllib.request.urlretrieve(url, tgz)
        if not tarfile.is_tarfile(tgz):
            raise RuntimeError("Download was not a tar archive")
        with tarfile.open(tgz, "r:gz") as tf:
            tf.extractall(work, filter="data")
        src = next((p for p in work.iterdir() if p.is_dir() and (p / "backend").is_dir()), None)
        if src is None:
            raise RuntimeError("Unexpected archive layout")
        _copy_tree(src / "backend", root / "backend")
        _copy_tree(src / "frontend", root / "frontend")
        if (src / "deploy").is_dir():
            _copy_tree(src / "deploy", root / "deploy")
        _write_version(APP_VERSION)
        if not skip_frontend:
            _build_frontend(root / "frontend")
        if not skip_restart:
            _restart_services()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"ok": "true", "version": APP_VERSION, "root": str(root)}


def schedule_restart() -> None:
    subprocess.Popen(
        ["bash", "-lc", "sleep 2; systemctl restart receiptvault receiptvault-worker || true"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _copy_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, dirs_exist_ok=True)


def _write_version(version: str) -> None:
    from app.config import upsert_env_key

    upsert_env_key("RECEIPTVAULT_APP_VERSION", version)


def _build_frontend(frontend: Path) -> None:
    if not shutil.which("npm"):
        raise RuntimeError("npm is not installed")
    cmd = ["npm", "ci", "--omit=optional"] if (frontend / "package-lock.json").exists() else ["npm", "install", "--omit=optional"]
    subprocess.run(cmd, cwd=frontend, check=True)
    subprocess.run(["npx", "vite", "build"], cwd=frontend, check=True)
    index = frontend / "dist" / "index.html"
    if not index.is_file():
        raise RuntimeError("UI build did not produce frontend/dist/index.html")


def _restart_services() -> None:
    if not shutil.which("systemctl"):
        return
    schedule_restart()
