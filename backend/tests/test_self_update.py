from __future__ import annotations

import tarfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.services.self_update import apply_update, production_install


def _bundle(tmp: Path, version_note: str = "updated") -> Path:
    src = tmp / "ReceiptVault-main"
    (src / "backend" / "app").mkdir(parents=True)
    (src / "frontend" / "src").mkdir(parents=True)
    (src / "deploy").mkdir(parents=True)
    (src / "backend" / "app" / "marker.txt").write_text(version_note)
    (src / "frontend" / "index.html").write_text("<html>ok</html>")
    (src / "deploy" / "guest-update.sh").write_text("#!/bin/bash\n")
    tgz = tmp / "main.tar.gz"
    with tarfile.open(tgz, "w:gz") as tf:
        tf.add(src, arcname="ReceiptVault-main")
    return tgz


def test_production_install_detects_tree(tmp_path: Path):
    assert production_install(tmp_path) is False
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    assert production_install(tmp_path) is True


def test_apply_update_copies_tree(tmp_path: Path, monkeypatch):
    root = tmp_path / "opt"
    (root / "backend" / "app").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "backend" / "app" / "old.txt").write_text("old")
    env = tmp_path / "receiptvault.env"
    env.write_text("RECEIPTVAULT_ENV=production\n")
    monkeypatch.setenv("RECEIPTVAULT_ENV_FILE", str(env))
    archive = _bundle(tmp_path, "from-github")
    result = apply_update(root=root, archive=archive, skip_frontend=True, skip_restart=True)
    assert result["version"] == "1.5.1"
    assert (root / "backend" / "app" / "marker.txt").read_text() == "from-github"
    assert "RECEIPTVAULT_APP_VERSION=1.5.1" in env.read_text()


def test_ops_update_rejected_outside_production(client: TestClient, owner):
    r = client.post("/api/v1/ops/update", json={}, headers={"X-CSRF-Token": owner["csrf"]})
    assert r.status_code == 409


def test_settings_reports_update_fields(client: TestClient, owner):
    r = client.get("/api/v1/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["app_version"] == "1.5.1"
    assert body["latest_bundle_version"] == "1.5.1"
    assert "can_self_update" in body
