from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user, require_csrf, settings_dep
from app.config import Settings
from app.db import get_db
from app.errors import AppError
from app.models import DuplicateGroup, DuplicateMember, EvidenceObject, ExtractedDocument, LineItem, TaxpayerPeriod, TaxpayerProfile, User
from app.services.audit import record_audit

router = APIRouter(tags=["review"])


class LinePatch(BaseModel):
    paid_personally: str | None = None
    reimbursed: str | None = None
    work_related: str | None = None
    work_use_percent: int | None = Field(default=None, ge=0, le=100)
    work_purpose: str | None = None
    decision: str | None = None
    adviser_note: str | None = None
    suggested_category: str | None = None


class ProfileBody(BaseModel):
    adviser_notes: str | None = None
    common_equipment: list[str] = []
    reimbursement_rules: str | None = None
    audit_years: list[str] = []
    periods: list[dict] = []


class CanonicalBody(BaseModel):
    evidence_id: str


@router.get("/review/queue")
def review_queue(user: User = Depends(current_user), db: Session = Depends(get_db)):
    lines = db.query(LineItem).filter(LineItem.decision == "undecided").order_by(LineItem.position).all()
    items = []
    for line in lines:
        doc = db.get(ExtractedDocument, line.document_id)
        ev = db.get(EvidenceObject, doc.evidence_id) if doc else None
        items.append(
            {
                "line_id": str(line.id),
                "evidence_id": str(ev.id) if ev else None,
                "filename": ev.display_filename if ev else None,
                "description": line.raw_description,
                "suggested_status": line.suggested_status,
                "decision": line.decision,
                "explanation": line.explanation,
            }
        )
    return {"items": items}


@router.patch("/review/lines/{line_id}")
def patch_line(
    line_id: str,
    body: LinePatch,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    line = db.get(LineItem, line_id)
    if not line:
        raise AppError(404, "Not found", "Line item missing")
    changes = {}
    for field in ("paid_personally", "reimbursed", "work_related", "work_purpose", "decision", "adviser_note", "suggested_category"):
        value = getattr(body, field)
        if value is not None:
            changes[field] = {"old": getattr(line, field), "new": value}
            setattr(line, field, value)
    if body.work_use_percent is not None:
        changes["work_use_percent"] = {"old": line.work_use_percent, "new": body.work_use_percent}
        line.work_use_percent = body.work_use_percent
    line.history = list(line.history or []) + [{"at": datetime.now(timezone.utc).isoformat(), "user": user.username, "changes": changes}]
    record_audit(db, event_type="classification_decision", success=True, user_id=user.id, target_id=line_id, ip=client_ip(request, settings))
    db.commit()
    return {"ok": True}


@router.get("/profile")
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = db.query(TaxpayerProfile).filter(TaxpayerProfile.user_id == user.id).one_or_none()
    if not profile:
        profile = TaxpayerProfile(user_id=user.id, common_equipment=[], audit_years=[])
        db.add(profile)
        db.commit()
        db.refresh(profile)
    periods = db.query(TaxpayerPeriod).filter(TaxpayerPeriod.profile_id == profile.id).all()
    return {
        "adviser_notes": profile.adviser_notes,
        "common_equipment": profile.common_equipment,
        "reimbursement_rules": profile.reimbursement_rules,
        "audit_years": profile.audit_years,
        "periods": [
            {
                "id": str(p.id),
                "role_title": p.role_title,
                "industry": p.industry,
                "employer": p.employer,
                "duties": p.duties,
                "location": p.location,
                "started_on": p.started_on,
                "ended_on": p.ended_on,
            }
            for p in periods
        ],
        "examples": "Add your own employment periods. Neutral example only: Software engineer, professional services.",
    }


@router.put("/profile")
def put_profile(body: ProfileBody, user: User = Depends(current_user), db: Session = Depends(get_db), request: Request = None, settings: Settings = Depends(settings_dep), _: None = Depends(require_csrf)):
    profile = db.query(TaxpayerProfile).filter(TaxpayerProfile.user_id == user.id).one_or_none()
    if not profile:
        profile = TaxpayerProfile(user_id=user.id)
        db.add(profile)
        db.flush()
    profile.adviser_notes = body.adviser_notes
    profile.common_equipment = body.common_equipment
    profile.reimbursement_rules = body.reimbursement_rules
    profile.audit_years = body.audit_years
    db.query(TaxpayerPeriod).filter(TaxpayerPeriod.profile_id == profile.id).delete()
    for period in body.periods:
        db.add(
            TaxpayerPeriod(
                profile_id=profile.id,
                role_title=period.get("role_title") or "Role",
                industry=period.get("industry"),
                employer=period.get("employer"),
                duties=period.get("duties"),
                location=period.get("location"),
            )
        )
    record_audit(db, event_type="settings_change", success=True, user_id=user.id, metadata={"area": "taxpayer_profile"}, ip=client_ip(request, settings) if request else None)
    db.commit()
    return {"ok": True}


@router.get("/duplicates")
def list_duplicates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    groups = db.query(DuplicateGroup).all()
    items = []
    for group in groups:
        members = db.query(DuplicateMember).filter(DuplicateMember.group_id == group.id).all()
        files = []
        for member in members:
            ev = db.get(EvidenceObject, member.evidence_id)
            if ev:
                files.append({"id": str(ev.id), "filename": ev.display_filename, "sha256": ev.sha256, "reason": member.reason})
        items.append(
            {
                "id": str(group.id),
                "kind": group.kind,
                "canonical_evidence_id": str(group.canonical_evidence_id) if group.canonical_evidence_id else None,
                "members": files,
            }
        )
    return {"items": items}


@router.post("/duplicates/{group_id}/canonical")
def set_canonical(group_id: str, body: CanonicalBody, user: User = Depends(current_user), db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    group = db.get(DuplicateGroup, group_id)
    if not group:
        raise AppError(404, "Not found", "Duplicate group missing")
    group.canonical_evidence_id = body.evidence_id
    db.commit()
    return {"ok": True}
