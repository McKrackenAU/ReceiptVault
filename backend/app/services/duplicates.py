from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import DuplicateGroup, DuplicateMember, EvidenceObject, ExtractedDocument


def probable_fingerprint(merchant: str | None, number: str | None, date, total: Decimal | None, currency: str) -> str:
    merchant_n = (merchant or "").strip().lower()
    number_n = (number or "").strip().lower()
    date_n = date.date().isoformat() if date else ""
    total_n = f"{total:.2f}" if total is not None else ""
    return "|".join([merchant_n, number_n, date_n, total_n, currency or ""])


def link_duplicates(db: Session, evidence: EvidenceObject, document: ExtractedDocument | None) -> None:
    exact = (
        db.query(EvidenceObject)
        .filter(EvidenceObject.sha256 == evidence.sha256, EvidenceObject.id != evidence.id, EvidenceObject.deleted_at.is_(None))
        .all()
    )
    if exact:
        _add_group(db, "exact", evidence.sha256, [evidence, *exact])
    if document:
        fp = probable_fingerprint(
            document.fields_json.get("merchant") if document.fields_json else None,
            document.document_number,
            document.document_date,
            document.total,
            document.currency,
        )
        if fp.strip("|"):
            others = (
                db.query(ExtractedDocument)
                .filter(ExtractedDocument.id != document.id)
                .all()
            )
            matches = []
            for other in others:
                other_fp = probable_fingerprint(
                    other.fields_json.get("merchant") if other.fields_json else None,
                    other.document_number,
                    other.document_date,
                    other.total,
                    other.currency,
                )
                if other_fp == fp and fp.count("|") >= 3:
                    ev = db.get(EvidenceObject, other.evidence_id)
                    if ev:
                        matches.append(ev)
            if matches:
                _add_group(db, "probable", fp, [evidence, *matches])


def _add_group(db: Session, kind: str, fingerprint: str, members: list[EvidenceObject]) -> None:
    group = db.query(DuplicateGroup).filter(DuplicateGroup.fingerprint == fingerprint).one_or_none()
    if not group:
        group = DuplicateGroup(kind=kind, fingerprint=fingerprint, canonical_evidence_id=None)
        db.add(group)
        db.flush()
    existing = {m.evidence_id for m in db.query(DuplicateMember).filter(DuplicateMember.group_id == group.id)}
    for member in members:
        if member.id in existing:
            continue
        db.add(DuplicateMember(group_id=group.id, evidence_id=member.id, reason=kind))
