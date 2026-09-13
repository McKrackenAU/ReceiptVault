from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import AuditEvent, User
from app.services.audit import export_audit_csv

router = APIRouter(tags=["audit"])


@router.get("/audit")
def list_audit(offset: int = 0, limit: int = 100, event_type: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(AuditEvent)
    if event_type:
        query = query.filter(AuditEvent.event_type == event_type)
    rows = query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [
            {
                "id": str(e.id),
                "created_at": e.created_at,
                "username": e.username,
                "event_type": e.event_type,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "success": e.success,
                "ip": e.ip,
                "metadata": e.metadata_json,
            }
            for e in rows
        ],
        "offset": offset,
        "limit": limit,
    }


@router.get("/audit.csv")
def audit_csv(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(10000).all()
    return Response(content=export_audit_csv(rows), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit-log.csv"})
