from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.crypto import sha256_bytes, sha256_file
from app.models import EvidenceObject, EvidenceRelationship, FolderMembership, VirtualFolder
from app.services.paths import content_addressed_relpath, resolve_under, safe_filename
from app.services.types import detect_file_type, is_previewable, is_rejected_active


def store_original(
    db: Session,
    settings: Settings,
    *,
    data: bytes,
    filename: str,
    kind: str,
    source_account_id=None,
    source_message_id=None,
    uploaded_by=None,
    parent_id=None,
    derived_from_id=None,
    is_original: bool = True,
) -> EvidenceObject:
    digest = sha256_bytes(data)
    existing = (
        db.query(EvidenceObject)
        .filter(EvidenceObject.sha256 == digest, EvidenceObject.deleted_at.is_(None), EvidenceObject.is_original.is_(True))
        .first()
    )
    display = safe_filename(filename)
    detected = detect_file_type(data, filename)
    relpath = content_addressed_relpath(digest, display)
    dest = resolve_under(settings.evidence_root if is_original else settings.derived_root, relpath)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)
        dest.chmod(0o444 if is_original else 0o644)
    unsupported = None
    if is_rejected_active(detected.media_type, filename):
        unsupported = "active_content_preserved_not_previewed"
    elif not is_previewable(detected.media_type):
        unsupported = "unsupported_preview"

    if existing and is_original:
        return existing

    obj = EvidenceObject(
        sha256=digest,
        byte_count=len(data),
        original_filename=filename,
        display_filename=display,
        media_type=detected.media_type,
        detected_type=detected.label,
        kind=kind,
        storage_relpath=relpath,
        source_account_id=source_account_id,
        source_message_id=source_message_id,
        uploaded_by=uploaded_by,
        parent_id=parent_id,
        derived_from_id=derived_from_id,
        is_original=is_original,
        unsupported_label=unsupported,
        processing_history=[{"event": "ingested", "at": datetime.now(timezone.utc).isoformat()}],
    )
    db.add(obj)
    db.flush()
    if parent_id:
        db.add(EvidenceRelationship(parent_id=parent_id, child_id=obj.id, relation="attachment"))
    if derived_from_id:
        db.add(EvidenceRelationship(parent_id=derived_from_id, child_id=obj.id, relation="derived"))
    return obj


def read_evidence_bytes(settings: Settings, obj: EvidenceObject) -> bytes:
    root = settings.evidence_root if obj.is_original else settings.derived_root
    path = resolve_under(root, obj.storage_relpath)
    return path.read_bytes()


def evidence_path(settings: Settings, obj: EvidenceObject) -> Path:
    root = settings.evidence_root if obj.is_original else settings.derived_root
    return resolve_under(root, obj.storage_relpath)


def verify_stored_hash(settings: Settings, obj: EvidenceObject) -> bool:
    return sha256_file(evidence_path(settings, obj)) == obj.sha256


def soft_delete(db: Session, settings: Settings, obj: EvidenceObject) -> None:
    now = datetime.now(timezone.utc)
    obj.deleted_at = now
    obj.purge_after = now + timedelta(days=settings.soft_delete_days)


def ensure_virtual_folder(db: Session, path: str, label: str, parent_path: str | None = None) -> VirtualFolder:
    folder = db.query(VirtualFolder).filter(VirtualFolder.path == path).one_or_none()
    if folder:
        return folder
    folder = VirtualFolder(path=path, label=label, parent_path=parent_path)
    db.add(folder)
    db.flush()
    return folder


def add_to_folder(db: Session, folder: VirtualFolder, evidence_id: uuid.UUID) -> None:
    exists = (
        db.query(FolderMembership)
        .filter(FolderMembership.folder_id == folder.id, FolderMembership.evidence_id == evidence_id)
        .one_or_none()
    )
    if exists:
        return
    db.add(FolderMembership(folder_id=folder.id, evidence_id=evidence_id))
