from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.crypto import sha256_file
from app.models import EvidenceObject, FolderMembership, Package, VirtualFolder
from app.services.evidence import evidence_path
from app.services.paths import safe_filename, safe_relpath


def build_folder_package(db: Session, settings: Settings, package: Package) -> None:
    folder_path = package.manifest.get("folder_path")
    folder = db.query(VirtualFolder).filter(VirtualFolder.path == folder_path).one_or_none()
    items = []
    if folder:
        items = _collect_folder(db, folder)
    else:
        ids = package.manifest.get("evidence_ids") or []
        items = [db.get(EvidenceObject, eid) for eid in ids]
        items = [item for item in items if item and not item.deleted_at]
    dest_dir = settings.staging_root / "packages"
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{package.id}.zip"
    archive = dest_dir / archive_name
    manifest_entries = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for obj in items:
            rel = safe_relpath(f"{obj.financial_year or 'unassigned'}/{obj.sha256[:8]}-{safe_filename(obj.display_filename)}")
            # Prevent zip slip: archive names are already sanitized relative paths.
            if rel.startswith("/") or ".." in Path(rel).parts:
                continue
            src = evidence_path(settings, obj)
            zf.write(src, rel)
            manifest_entries.append(
                {
                    "path": rel,
                    "sha256": obj.sha256,
                    "bytes": obj.byte_count,
                    "source_id": str(obj.id),
                }
            )
            package.progress = min(99, int(100 * len(manifest_entries) / max(len(items), 1)))
        zf.writestr(
            "MANIFEST.json",
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "entries": manifest_entries,
                },
                indent=2,
            ),
        )
    package.archive_relpath = f"packages/{archive_name}"
    package.byte_count = archive.stat().st_size
    package.sha256 = sha256_file(archive)
    package.manifest = {**package.manifest, "entries": manifest_entries, "generated_at": datetime.now(timezone.utc).isoformat()}
    package.status = "ready"
    package.progress = 100
    package.expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.package_expiry_hours)


def _collect_folder(db: Session, folder: VirtualFolder) -> list[EvidenceObject]:
    members = db.query(FolderMembership).filter(FolderMembership.folder_id == folder.id).all()
    items = []
    for member in members:
        obj = db.get(EvidenceObject, member.evidence_id)
        if obj and not obj.deleted_at:
            items.append(obj)
    children = db.query(VirtualFolder).filter(VirtualFolder.parent_path == folder.path).all()
    for child in children:
        items.extend(_collect_folder(db, child))
    seen: set = set()
    unique = []
    for obj in items:
        if obj.id in seen:
            continue
        seen.add(obj.id)
        unique.append(obj)
    return unique
