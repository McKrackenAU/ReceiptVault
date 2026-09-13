from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import Settings
from app.crypto import sha256_bytes
from app.errors import AppError
from app.models import TransferChunk, TransferSession
from app.services.ingest import ingest_bytes
from app.services.paths import resolve_under, safe_filename


def create_upload_session(
    db: Session,
    settings: Settings,
    user_id,
    *,
    filename: str,
    size: int,
    relative_path: str | None,
    mime_hint: str | None,
    sha256: str | None,
) -> TransferSession:
    if size < 0:
        raise AppError(400, "Invalid size", "Upload size must be >= 0")
    max_bytes = settings.max_upload_mib * 1024 * 1024
    if size > max_bytes:
        raise AppError(413, "Too large", "File exceeds configured per-file limit")
    free = _free_bytes(settings.staging_root)
    if free < size + settings.chunk_size_bytes:
        raise AppError(507, "Insufficient storage", "Not enough free space for this upload")
    session = TransferSession(
        user_id=user_id,
        direction="upload",
        filename=safe_filename(filename),
        relative_path=relative_path,
        mime_hint=mime_hint,
        total_size=size,
        chunk_size=settings.chunk_size_bytes,
        expected_sha256=sha256,
        uploaded_parts={},
        status="open",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.transfer_session_hours),
    )
    db.add(session)
    db.flush()
    staging = _session_dir(settings, session.id)
    staging.mkdir(parents=True, exist_ok=True)
    return session


def receive_chunk(db: Session, settings: Settings, session: TransferSession, index: int, data: bytes, digest: str) -> None:
    _assert_open(session)
    if sha256_bytes(data) != digest:
        raise AppError(400, "Chunk hash mismatch", "Per-chunk SHA-256 did not match")
    if len(data) > session.chunk_size:
        raise AppError(413, "Chunk too large", "Chunk exceeds negotiated size")
    path = _session_dir(settings, session.id) / f"{index:08d}.part"
    path.write_bytes(data)
    parts = dict(session.uploaded_parts or {})
    parts[str(index)] = {"sha256": digest, "size": len(data)}
    session.uploaded_parts = parts
    flag_modified(session, "uploaded_parts")
    existing = (
        db.query(TransferChunk).filter(TransferChunk.session_id == session.id, TransferChunk.index == index).one_or_none()
    )
    if existing:
        existing.sha256 = digest
        existing.size = len(data)
    else:
        db.add(TransferChunk(session_id=session.id, index=index, sha256=digest, size=len(data)))


def finalize_upload(db: Session, settings: Settings, session: TransferSession, user_id) -> object:
    _assert_open(session)
    expected_parts = _expected_part_count(session.total_size, session.chunk_size)
    have = {int(k) for k in session.uploaded_parts}
    missing = [i for i in range(expected_parts) if i not in have]
    if session.total_size == 0:
        missing = []
    if missing:
        raise AppError(409, "Incomplete upload", "Missing chunks", extra={"missing": missing})
    dest = _session_dir(settings, session.id) / "assembled.bin"
    with dest.open("wb") as out:
        if session.total_size == 0:
            out.write(b"")
        else:
            for index in range(expected_parts):
                part = _session_dir(settings, session.id) / f"{index:08d}.part"
                out.write(part.read_bytes())
    assembled = dest.read_bytes()
    if len(assembled) != session.total_size:
        raise AppError(400, "Size mismatch", "Assembled size does not match declared size")
    digest = sha256_bytes(assembled)
    if session.expected_sha256 and session.expected_sha256 != digest:
        raise AppError(400, "File hash mismatch", "Whole-file SHA-256 did not match")
    document = ingest_bytes(db, settings, data=assembled, filename=session.filename, kind="upload", uploaded_by=user_id)
    session.status = "finalized"
    session.object_id = document.evidence_id
    session.version = digest
    _cleanup_session_dir(settings, session.id)
    return document


def cancel_session(db: Session, settings: Settings, session: TransferSession) -> None:
    session.status = "cancelled"
    _cleanup_session_dir(settings, session.id)


def missing_chunks(session: TransferSession) -> list[int]:
    expected = _expected_part_count(session.total_size, session.chunk_size)
    have = {int(k) for k in session.uploaded_parts}
    return [i for i in range(expected) if i not in have]


def _expected_part_count(size: int, chunk: int) -> int:
    if size == 0:
        return 0
    return (size + chunk - 1) // chunk


def _assert_open(session: TransferSession) -> None:
    if session.status != "open":
        raise AppError(409, "Session closed", "Transfer session is not open")
    if session.expires_at <= datetime.now(timezone.utc):
        session.status = "expired"
        raise AppError(410, "Expired", "Transfer session expired")


def _session_dir(settings: Settings, session_id: uuid.UUID) -> Path:
    return resolve_under(settings.staging_root, f"uploads/{session_id}")


def _cleanup_session_dir(settings: Settings, session_id: uuid.UUID) -> None:
    path = settings.staging_root / "uploads" / str(session_id)
    if path.exists():
        for child in path.glob("*"):
            child.unlink()
        path.rmdir()


def _free_bytes(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    import os

    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize


def cleanup_expired(db: Session, settings: Settings) -> int:
    now = datetime.now(timezone.utc)
    expired = db.query(TransferSession).filter(TransferSession.expires_at < now, TransferSession.status == "open").all()
    for session in expired:
        session.status = "expired"
        _cleanup_session_dir(settings, session.id)
    return len(expired)
