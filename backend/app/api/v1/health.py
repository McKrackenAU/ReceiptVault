from __future__ import annotations

import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import current_user, settings_dep
from app.config import Settings
from app.db import get_db
from app.models import MailboxAccount, ProcessingJob, User

router = APIRouter(tags=["health"])


@router.get("/health")
def health(user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    redis_ok = True
    try:
        import redis

        redis.Redis.from_url(settings.redis_url).ping()
    except Exception:
        redis_ok = False
    usage = shutil.disk_usage(settings.evidence_root)
    pending = db.query(ProcessingJob).filter(ProcessingJob.status.in_(["queued", "running"])).count()
    failed = db.query(ProcessingJob).filter(ProcessingJob.status == "failed").count()
    accounts = db.query(MailboxAccount).filter(MailboxAccount.disconnected_at.is_(None)).all()
    staging = sum(p.stat().st_size for p in settings.staging_root.rglob("*") if p.is_file()) if settings.staging_root.exists() else 0
    return {
        "app": settings.app_version,
        "time": datetime.now(timezone.utc).isoformat(),
        "database": "ok" if db_ok else "error",
        "queue": "ok" if redis_ok else "error",
        "worker_heartbeat": "inline-or-dramatiq",
        "mail": [{"label": a.label, "status": a.scan_status, "last_scan_at": a.last_scan_at} for a in accounts],
        "storage_free_bytes": usage.free,
        "staging_bytes": staging,
        "pending_jobs": pending,
        "failed_jobs": failed,
    }
