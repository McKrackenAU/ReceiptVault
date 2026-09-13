from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user, require_csrf, settings_dep
from app.config import Settings
from app.db import get_db
from app.errors import AppError
from app.models import EvidenceObject, EvidenceRelationship, ExtractedDocument, ExtractedField, FolderMembership, LineItem, User, VirtualFolder
from app.services.audit import record_audit
from app.services.email_view import is_email_media, parse_email_view
from app.services.evidence import read_evidence_bytes, soft_delete
from app.services.html_sanitize import sanitize_email_html
from app.services.ingest import ingest_bytes

router = APIRouter(tags=["documents"])


class DeleteBody(BaseModel):
    confirmation: str


class FieldPatch(BaseModel):
    value: str


@router.get("/documents")
def list_documents(
    q: str | None = None,
    financial_year: str | None = None,
    status: str | None = None,
    supplier: str | None = None,
    file_type: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    inbox: str | None = None,
    folder: str | None = None,
    offset: int = 0,
    limit: int = 50,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(EvidenceObject).filter(EvidenceObject.deleted_at.is_(None))
    if financial_year:
        query = query.filter(EvidenceObject.financial_year == financial_year)
    if file_type:
        query = query.filter(EvidenceObject.detected_type.contains(file_type))
    if q:
        docs = db.query(ExtractedDocument).filter(
            or_(ExtractedDocument.raw_text.ilike(f"%{q}%"), ExtractedDocument.normalized_text.ilike(f"%{q}%"))
        )
        ids = [d.evidence_id for d in docs]
        query = query.filter(or_(EvidenceObject.id.in_(ids), EvidenceObject.display_filename.ilike(f"%{q}%")))
    if folder:
        vf = db.query(VirtualFolder).filter(VirtualFolder.path == folder).one_or_none()
        if vf:
            member_ids = [m.evidence_id for m in db.query(FolderMembership).filter(FolderMembership.folder_id == vf.id)]
            query = query.filter(EvidenceObject.id.in_(member_ids))
    items = query.order_by(EvidenceObject.ingested_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [_doc_summary(db, obj) for obj in items],
        "offset": offset,
        "limit": limit,
        "total": query.count(),
    }


@router.get("/documents/{evidence_id}")
def get_document(evidence_id: str, user: User = Depends(current_user), db: Session = Depends(get_db), request: Request = None, settings: Settings = Depends(settings_dep)):
    obj = _get(db, evidence_id)
    record_audit(db, event_type="document_view", success=True, user_id=user.id, target_id=evidence_id, ip=client_ip(request, settings) if request else None)
    db.commit()
    doc = db.query(ExtractedDocument).filter(ExtractedDocument.evidence_id == obj.id).one_or_none()
    fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).all() if doc else []
    lines = db.query(LineItem).filter(LineItem.document_id == doc.id).order_by(LineItem.position).all() if doc else []
    return {
        **_doc_summary(db, obj),
        "sha256": obj.sha256,
        "bytes": obj.byte_count,
        "processing_history": obj.processing_history,
        "extracted": _extracted_payload(doc) if doc else None,
        "fields": [
            {"id": str(f.id), "name": f.name, "raw": f.raw_value, "current": f.current_value, "confidence": str(f.confidence) if f.confidence is not None else None, "page": f.page_number, "history": f.history}
            for f in fields
        ],
        "line_items": [_line_payload(line) for line in lines],
        "related": _related(db, obj),
    }


@router.get("/documents/{evidence_id}/content")
def download_content(evidence_id: str, request: Request, disposition: str = "inline", user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    obj = _get(db, evidence_id)
    data = read_evidence_bytes(settings, obj)
    record_audit(db, event_type="document_download", success=True, user_id=user.id, target_id=evidence_id, ip=client_ip(request, settings))
    db.commit()
    headers = {
        "ETag": f'"{obj.sha256}"',
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'{disposition}; filename="{obj.display_filename}"',
        "X-Content-SHA256": obj.sha256,
    }
    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        spec = range_header.split("=", 1)[1]
        start_s, end_s = (spec.split("-") + [""])[:2]
        start = int(start_s or 0)
        end = int(end_s) if end_s else len(data) - 1
        chunk = data[start : end + 1]
        headers["Content-Range"] = f"bytes {start}-{start + len(chunk) - 1}/{len(data)}"
        return Response(content=chunk, status_code=206, media_type=obj.media_type, headers=headers)
    return Response(content=data, media_type=obj.media_type, headers=headers)


@router.get("/documents/{evidence_id}/preview")
def document_preview(evidence_id: str, user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    obj = _get(db, evidence_id)
    data = read_evidence_bytes(settings, obj)
    related = _related(db, obj)
    payload = {
        "id": str(obj.id),
        "filename": obj.display_filename,
        "media_type": obj.media_type,
        "kind": obj.kind,
        "bytes": obj.byte_count,
        "viewer": _viewer_kind(obj),
        "related": related,
        "email": None,
        "text": None,
    }
    if is_email_media(obj.media_type, obj.display_filename):
        payload["email"] = parse_email_view(data)
    elif obj.media_type.startswith("text/") or obj.media_type == "text/html":
        raw = data.decode("utf-8", "ignore")
        payload["text"] = sanitize_email_html(raw) if obj.media_type == "text/html" else raw
    return payload


@router.get("/documents/{evidence_id}/html")
def sanitized_html(evidence_id: str, user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    obj = _get(db, evidence_id)
    data = read_evidence_bytes(settings, obj)
    if is_email_media(obj.media_type, obj.display_filename):
        body = parse_email_view(data)["html"]
    elif obj.media_type == "text/html":
        body = sanitize_email_html(data.decode("utf-8", "ignore"))
    else:
        import html as html_mod

        body = f"<pre>{html_mod.escape(data.decode('utf-8', 'ignore'))}</pre>"
    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='referrer' content='no-referrer'>"
        "<style>body{font-family:system-ui,sans-serif;margin:1rem;color:#1a1a1a}"
        "pre{white-space:pre-wrap;word-break:break-word}</style>"
        "</head><body>"
        f"{body}"
        "</body></html>"
    )
    return HTMLResponse(
        page,
        headers={
            "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'none'; frame-ancestors 'self'",
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


@router.post("/documents/upload")
async def upload_small(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        raise AppError(400, "Missing file", "file field required")
    data = await upload.read()
    filename = getattr(upload, "filename", "upload.bin")
    if len(data) > settings.chunk_size_bytes:
        raise AppError(413, "Use chunked upload", "File larger than one chunk; create a transfer session")
    doc = ingest_bytes(db, settings, data=data, filename=filename, kind="upload", uploaded_by=user.id)
    record_audit(db, event_type="document_upload", success=True, user_id=user.id, target_id=str(doc.evidence_id), ip=client_ip(request, settings))
    db.commit()
    return {"evidence_id": str(doc.evidence_id)}


@router.post("/documents/{evidence_id}/delete")
def delete_document(
    evidence_id: str,
    body: DeleteBody,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    obj = _get(db, evidence_id)
    if body.confirmation != obj.display_filename:
        raise AppError(400, "Confirmation failed", "Type the exact display filename to delete")
    soft_delete(db, settings, obj)
    record_audit(db, event_type="document_delete", success=True, user_id=user.id, target_id=evidence_id, ip=client_ip(request, settings))
    db.commit()
    return {"ok": True, "purge_after": obj.purge_after}


@router.patch("/documents/{evidence_id}/fields/{field_id}")
def patch_field(
    evidence_id: str,
    field_id: str,
    body: FieldPatch,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    field = db.get(ExtractedField, field_id)
    if not field:
        raise AppError(404, "Not found", "Field missing")
    old = field.current_value
    field.current_value = body.value
    field.history = list(field.history or []) + [
        {"old": old, "new": body.value, "at": datetime.now(timezone.utc).isoformat(), "user": user.username}
    ]
    record_audit(db, event_type="metadata_change", success=True, user_id=user.id, target_id=evidence_id, ip=client_ip(request, settings), metadata={"field": field.name})
    db.commit()
    return {"ok": True, "raw": field.raw_value, "current": field.current_value}


@router.get("/folders")
def list_folders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    folders = db.query(VirtualFolder).order_by(VirtualFolder.path).all()
    return {"items": [{"id": str(f.id), "path": f.path, "label": f.label, "parent_path": f.parent_path} for f in folders]}


def _viewer_kind(obj: EvidenceObject) -> str:
    media = obj.media_type or ""
    if is_email_media(media, obj.display_filename):
        return "email"
    if media == "application/pdf":
        return "pdf"
    if media.startswith("image/"):
        return "image"
    if media == "text/html":
        return "html"
    if media.startswith("text/"):
        return "text"
    return "file"


def _related(db: Session, obj: EvidenceObject) -> dict:
    children = (
        db.query(EvidenceObject)
        .filter(EvidenceObject.parent_id == obj.id, EvidenceObject.deleted_at.is_(None))
        .all()
    )
    rel_ids = [
        r.child_id
        for r in db.query(EvidenceRelationship).filter(EvidenceRelationship.parent_id == obj.id).all()
    ]
    extra = db.query(EvidenceObject).filter(EvidenceObject.id.in_(rel_ids), EvidenceObject.deleted_at.is_(None)).all() if rel_ids else []
    seen = {c.id for c in children}
    for item in extra:
        if item.id not in seen:
            children.append(item)
            seen.add(item.id)
    parent = db.get(EvidenceObject, obj.parent_id) if obj.parent_id else None
    if parent and parent.deleted_at:
        parent = None
    return {
        "parent": _related_item(parent) if parent else None,
        "attachments": [_related_item(c) for c in children],
    }


def _related_item(obj: EvidenceObject) -> dict:
    return {
        "id": str(obj.id),
        "filename": obj.display_filename,
        "media_type": obj.media_type,
        "kind": obj.kind,
        "bytes": obj.byte_count,
        "viewer": _viewer_kind(obj),
    }


def _get(db: Session, evidence_id: str) -> EvidenceObject:
    obj = db.get(EvidenceObject, evidence_id)
    if not obj or obj.deleted_at:
        raise AppError(404, "Not found", "Document missing")
    return obj


def _doc_summary(db: Session, obj: EvidenceObject) -> dict:
    doc = db.query(ExtractedDocument).filter(ExtractedDocument.evidence_id == obj.id).one_or_none()
    return {
        "id": str(obj.id),
        "filename": obj.display_filename,
        "original_filename": obj.original_filename,
        "kind": obj.kind,
        "media_type": obj.media_type,
        "financial_year": obj.financial_year,
        "fy_source": obj.fy_source,
        "ingested_at": obj.ingested_at,
        "unsupported_label": obj.unsupported_label,
        "is_original": obj.is_original,
        "parent_id": str(obj.parent_id) if obj.parent_id else None,
        "merchant": (doc.fields_json or {}).get("merchant") if doc else None,
        "total": str(doc.total) if doc and doc.total is not None else None,
        "currency": doc.currency if doc else None,
        "validation_flags": doc.validation_flags if doc else [],
    }


def _extracted_payload(doc: ExtractedDocument) -> dict:
    return {
        "id": str(doc.id),
        "doc_type": doc.doc_type,
        "document_number": doc.document_number,
        "document_date": doc.document_date,
        "currency": doc.currency,
        "subtotal": str(doc.subtotal) if doc.subtotal is not None else None,
        "tax": str(doc.tax) if doc.tax is not None else None,
        "total": str(doc.total) if doc.total is not None else None,
        "payment_masked": doc.payment_masked,
        "ocr_confidence": str(doc.ocr_confidence) if doc.ocr_confidence is not None else None,
        "engine_version": doc.engine_version,
        "raw_text": doc.raw_text,
        "validation_flags": doc.validation_flags,
        "disclaimer": "Organisational review aid only. Not tax or legal advice.",
    }


def _line_payload(line: LineItem) -> dict:
    return {
        "id": str(line.id),
        "position": line.position,
        "raw_description": line.raw_description,
        "normalized_description": line.normalized_description,
        "quantity": str(line.quantity) if line.quantity is not None else None,
        "unit_price": str(line.unit_price) if line.unit_price is not None else None,
        "line_total": str(line.line_total) if line.line_total is not None else None,
        "suggested_status": line.suggested_status,
        "suggested_category": line.suggested_category,
        "suggestion_confidence": str(line.suggestion_confidence) if line.suggestion_confidence is not None else None,
        "explanation": line.explanation,
        "paid_personally": line.paid_personally,
        "reimbursed": line.reimbursed,
        "work_related": line.work_related,
        "work_use_percent": line.work_use_percent,
        "work_purpose": line.work_purpose,
        "decision": line.decision,
        "adviser_note": line.adviser_note,
    }
