from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_csrf, settings_dep
from app.config import Settings
from app.crypto import sha256_file
from app.db import get_db
from app.errors import AppError
from app.models import Package, TransferSession, User
from app.services.jobs import create_job
from app.services.packages import build_folder_package
from app.services.transfers import (
    cancel_session,
    create_upload_session,
    finalize_upload,
    missing_chunks,
    receive_chunk,
)

router = APIRouter(tags=["transfers"])


class UploadSessionBody(BaseModel):
    filename: str
    size: int = Field(ge=0)
    relative_path: str | None = None
    mime_hint: str | None = None
    sha256: str | None = None


class PackageBody(BaseModel):
    folder_path: str | None = None
    evidence_ids: list[str] = []
    idempotency_key: str | None = None


@router.post("/transfers/uploads")
def open_upload(
    body: UploadSessionBody,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    session = create_upload_session(
        db,
        settings,
        user.id,
        filename=body.filename,
        size=body.size,
        relative_path=body.relative_path,
        mime_hint=body.mime_hint,
        sha256=body.sha256,
    )
    db.commit()
    return {
        "session_id": str(session.id),
        "chunk_size": session.chunk_size,
        "expires_at": session.expires_at,
        "uploaded_parts": session.uploaded_parts,
    }


@router.get("/transfers/uploads/{session_id}")
def upload_status(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _session(db, session_id, user)
    return {
        "session_id": str(session.id),
        "status": session.status,
        "uploaded_parts": session.uploaded_parts,
        "missing": missing_chunks(session),
        "chunk_size": session.chunk_size,
        "expires_at": session.expires_at,
    }


@router.put("/transfers/uploads/{session_id}/chunks/{index}")
async def put_chunk(
    session_id: str,
    index: int,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    session = _session(db, session_id, user)
    digest = request.headers.get("x-chunk-sha256")
    if not digest:
        raise AppError(400, "Missing hash", "X-Chunk-SHA256 required")
    data = await request.body()
    receive_chunk(db, settings, session, index, data, digest)
    db.commit()
    return {"ok": True, "missing": missing_chunks(session)}


@router.post("/transfers/uploads/{session_id}/finalize")
def finalize(
    session_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    session = _session(db, session_id, user)
    document = finalize_upload(db, settings, session, user.id)
    db.commit()
    return {"ok": True, "evidence_id": str(document.evidence_id)}


@router.post("/transfers/uploads/{session_id}/cancel")
def cancel(
    session_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    session = _session(db, session_id, user)
    cancel_session(db, settings, session)
    db.commit()
    return {"ok": True}


@router.post("/transfers/packages")
def create_package(
    body: PackageBody,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    job = create_job(db, "package", {"folder_path": body.folder_path, "evidence_ids": body.evidence_ids}, body.idempotency_key)
    package = Package(
        user_id=user.id,
        kind="folder" if body.folder_path else "selection",
        status="queued",
        manifest={"folder_path": body.folder_path, "evidence_ids": body.evidence_ids},
    )
    db.add(package)
    db.flush()
    build_folder_package(db, settings, package)
    job.status = "succeeded"
    db.commit()
    return {"package_id": str(package.id), "status": package.status, "bytes": package.byte_count, "sha256": package.sha256}


@router.get("/transfers/packages/{package_id}")
def package_status(package_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    package = db.get(Package, package_id)
    if not package or package.user_id != user.id:
        raise AppError(404, "Not found", "Package missing")
    return {
        "id": str(package.id),
        "status": package.status,
        "progress": package.progress,
        "bytes": package.byte_count,
        "sha256": package.sha256,
        "expires_at": package.expires_at,
        "manifest": package.manifest,
    }


@router.get("/transfers/packages/{package_id}/download")
def download_package(package_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    package = db.get(Package, package_id)
    if not package or package.user_id != user.id or package.status != "ready" or not package.archive_relpath:
        raise AppError(404, "Not found", "Package not ready")
    path = settings.staging_root / package.archive_relpath
    if not path.exists():
        raise AppError(404, "Not found", "Archive missing")
    if package.sha256 and sha256_file(path) != package.sha256:
        raise AppError(409, "Changed", "Package content changed; resume rejected")
    data = path.read_bytes()
    headers = {
        "ETag": f'"{package.sha256}"',
        "Accept-Ranges": "bytes",
        "X-Content-SHA256": package.sha256 or "",
        "Content-Disposition": f'attachment; filename="receiptvault-{package_id}.zip"',
    }
    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        spec = range_header.split("=", 1)[1]
        start_s, end_s = (spec.split("-") + [""])[:2]
        start = int(start_s or 0)
        end = int(end_s) if end_s else len(data) - 1
        chunk = data[start : end + 1]
        headers["Content-Range"] = f"bytes {start}-{start + len(chunk) - 1}/{len(data)}"
        return Response(content=chunk, status_code=206, media_type="application/zip", headers=headers)
    return FileResponse(path, media_type="application/zip", headers=headers, filename=f"receiptvault-{package_id}.zip")


def _session(db: Session, session_id: str, user: User) -> TransferSession:
    session = db.get(TransferSession, session_id)
    if not session or session.user_id != user.id:
        raise AppError(404, "Not found", "Transfer session missing")
    if session.expires_at <= datetime.now(timezone.utc) and session.status == "open":
        session.status = "expired"
        raise AppError(410, "Expired", "Transfer session expired")
    return session
