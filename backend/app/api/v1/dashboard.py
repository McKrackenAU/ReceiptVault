from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.db import get_db
from app.models import EvidenceObject, ExtractedDocument, LineItem, MailboxAccount, ProcessingJob, User

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(financial_year: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    accounts = db.query(MailboxAccount).filter(MailboxAccount.disconnected_at.is_(None)).all()
    jobs = db.query(ProcessingJob).filter(ProcessingJob.status.in_(["queued", "running"])).all()
    ev_q = db.query(EvidenceObject).filter(EvidenceObject.deleted_at.is_(None), EvidenceObject.is_original.is_(True))
    if financial_year:
        ev_q = ev_q.filter(EvidenceObject.financial_year == financial_year)
    evidence_count = ev_q.count()
    status_counts = dict(
        db.query(LineItem.suggested_status, func.count(LineItem.id)).group_by(LineItem.suggested_status).all()
    )
    undecided = db.query(LineItem).filter(LineItem.decision == "undecided").count()
    totals = {}
    docs = db.query(ExtractedDocument).all()
    for doc in docs:
        ev = db.get(EvidenceObject, doc.evidence_id)
        if not ev or ev.deleted_at:
            continue
        if financial_year and ev.financial_year != financial_year:
            continue
        key = ev.financial_year or "unassigned"
        totals.setdefault(key, 0)
        if doc.total is not None:
            totals[key] += float(doc.total)
    return {
        "financial_year": financial_year,
        "accounts": [
            {
                "id": str(a.id),
                "label": a.label,
                "masked_address": a.masked_address,
                "scan_status": a.scan_status,
                "last_scan_at": a.last_scan_at,
                "emails_examined": a.emails_examined,
                "candidates_found": a.candidates_found,
                "documents_imported": a.documents_imported,
                "failures": a.failures,
            }
            for a in accounts
        ],
        "active_jobs": [{"id": str(j.id), "kind": j.kind, "status": j.status, "progress": j.progress} for j in jobs],
        "receipts_found": evidence_count,
        "status_counts": status_counts,
        "unresolved_reviews": undecided,
        "totals_by_year": totals,
        "disclaimer": "Totals are extracted amounts for review. They are not final deductions and not tax advice.",
    }
