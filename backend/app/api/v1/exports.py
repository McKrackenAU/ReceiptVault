from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_csrf, settings_dep
from app.config import Settings
from app.db import get_db
from app.models import ExportRecord, Package, User
from app.services.exports import run_export
from app.services.jobs import create_job

router = APIRouter(tags=["exports"])


class ExportBody(BaseModel):
    financial_year: str | None = None
    evidence_ids: list[str] = []
    idempotency_key: str | None = None


@router.get("/exports")
def list_exports(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(ExportRecord).order_by(ExportRecord.created_at.desc()).limit(50).all()
    items = []
    for row in rows:
        package = db.get(Package, row.package_id) if row.package_id else None
        items.append(
            {
                "id": str(row.id),
                "financial_year": row.financial_year,
                "created_at": row.created_at,
                "package_id": str(row.package_id) if row.package_id else None,
                "status": package.status if package else "pending",
                "sha256": package.sha256 if package else None,
            }
        )
    return {"items": items}


@router.post("/exports")
def create_export(
    body: ExportBody,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    job = create_job(db, "export", {"financial_year": body.financial_year, "evidence_ids": body.evidence_ids}, body.idempotency_key)
    package = Package(user_id=user.id, kind="export", status="queued", manifest={})
    db.add(package)
    db.flush()
    export = ExportRecord(user_id=user.id, financial_year=body.financial_year, selection={"evidence_ids": body.evidence_ids}, job_id=job.id, package_id=package.id)
    db.add(export)
    db.flush()
    run_export(db, settings, export, package)
    job.status = "succeeded"
    db.commit()
    return {"export_id": str(export.id), "package_id": str(package.id), "sha256": package.sha256}
